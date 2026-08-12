from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.action_plan import ActionPlanMeasurement
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.engagement import AchievementGrant, AchievementPreference
from app.services.data_connections_service import GOOGLE_SEARCH_CONSOLE_PROVIDER
from app.services.google_business_profile_service import GOOGLE_BUSINESS_PROFILE_PROVIDER
from app.services.product_analytics_service import record_server_event_safely


RULE_VERSION = "1.0"
SUPPORTED_LIVE_PROVIDERS = {
    GOOGLE_SEARCH_CONSOLE_PROVIDER,
    GOOGLE_BUSINESS_PROFILE_PROVIDER,
}


class EngagementError(RuntimeError):
    def __init__(self, message: str, *, status_code: int, reason_code: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reason_code = reason_code


@dataclass(frozen=True)
class EligibleAchievement:
    rule_key: str
    category: str
    title: str
    description: str
    qualified_at: datetime
    evidence: list[dict[str, Any]]


FOUNDATION_RULES = (
    {
        "rule_key": "foundation.location_ready",
        "title": "Location ready",
        "description": "The business location, service area, and website are ready to measure.",
    },
    {
        "rule_key": "foundation.first_live_sync",
        "title": "Live results connected",
        "description": "InsightOS received the first successful update for this location.",
    },
    {
        "rule_key": "foundation.first_trustworthy_baseline",
        "title": "Starting point saved",
        "description": "A measured starting point is saved so future work can be checked fairly.",
    },
)


def _as_utc(value: datetime | None) -> datetime:
    resolved = value or datetime.now(UTC)
    if resolved.tzinfo is None:
        return resolved.replace(tzinfo=UTC)
    return resolved.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value is not None else None


def _evidence_digest(evidence: list[dict[str, Any]]) -> str:
    encoded = json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _campaign_and_location(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
) -> tuple[Campaign, BusinessLocation]:
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.organization_id == organization_id,
        )
        .first()
    )
    if campaign is None:
        raise EngagementError(
            "Campaign not found in this organization.",
            status_code=404,
            reason_code="campaign_not_found",
        )
    if campaign.business_location_id is None:
        raise EngagementError(
            "This campaign is not matched to a business location yet.",
            status_code=409,
            reason_code="campaign_location_missing",
        )
    location = (
        db.query(BusinessLocation)
        .filter(
            BusinessLocation.id == campaign.business_location_id,
            BusinessLocation.organization_id == organization_id,
        )
        .first()
    )
    if location is None:
        raise EngagementError(
            "The matched business location could not be found.",
            status_code=409,
            reason_code="business_location_missing",
        )
    return campaign, location


def _location_ready(
    campaign: Campaign,
    location: BusinessLocation,
) -> EligibleAchievement | None:
    domain = (location.domain or campaign.domain or "").strip()
    service_area = (
        location.city
        or location.primary_city
        or location.postal_code
        or location.region
        or ""
    ).strip()
    if location.status != "active" or not location.name.strip() or not domain or not service_area:
        return None
    evidence = [
        {
            "evidence_type": "location_setup",
            "business_location_id": location.id,
            "campaign_id": campaign.id,
            "location_name": location.name,
            "website": domain,
            "service_area": service_area,
            "status": location.status,
        }
    ]
    return EligibleAchievement(
        rule_key="foundation.location_ready",
        category="foundation",
        title="Location ready",
        description="The business location, service area, and website are ready to measure.",
        qualified_at=_as_utc(location.updated_at or location.created_at),
        evidence=evidence,
    )


def _first_live_sync(
    db: Session,
    *,
    organization_id: str,
    campaign: Campaign,
    location: BusinessLocation,
) -> EligibleAchievement | None:
    connection = (
        db.query(DataConnection)
        .filter(
            DataConnection.organization_id == organization_id,
            DataConnection.campaign_id == campaign.id,
            DataConnection.business_location_id == location.id,
            DataConnection.provider_name.in_(SUPPORTED_LIVE_PROVIDERS),
            DataConnection.status == "connected",
            DataConnection.last_success_at.is_not(None),
        )
        .order_by(DataConnection.last_success_at.asc(), DataConnection.id.asc())
        .first()
    )
    if connection is None or connection.last_success_at is None:
        return None
    evidence = [
        {
            "evidence_type": "successful_data_sync",
            "connection_id": connection.id,
            "business_location_id": location.id,
            "campaign_id": campaign.id,
            "source": "website_results"
            if connection.provider_name == GOOGLE_SEARCH_CONSOLE_PROVIDER
            else "business_profile_results",
            "successful_at": _iso(connection.last_success_at),
        }
    ]
    return EligibleAchievement(
        rule_key="foundation.first_live_sync",
        category="foundation",
        title="Live results connected",
        description="InsightOS received the first successful update for this location.",
        qualified_at=_as_utc(connection.last_success_at),
        evidence=evidence,
    )


def _trustworthy_metric(measurement: ActionPlanMeasurement) -> dict[str, Any] | None:
    contract = dict(measurement.measurement_contract or {})
    primary_metric_id = contract.get("primary_metric_id")
    if not primary_metric_id or not contract.get("version") or not contract.get("track"):
        return None
    for item in list(measurement.baseline_metrics or []):
        if not isinstance(item, dict) or item.get("status") != "available":
            continue
        if item.get("metric_id") != primary_metric_id:
            continue
        if item.get("value") is None:
            continue
        if not (
            item.get("source_record_id")
            or item.get("source")
            or measurement.baseline_evidence
        ):
            continue
        return item
    return None


def _first_trustworthy_baseline(
    db: Session,
    *,
    organization_id: str,
    campaign: Campaign,
    location: BusinessLocation,
) -> EligibleAchievement | None:
    rows = (
        db.query(ActionPlanMeasurement)
        .filter(
            ActionPlanMeasurement.organization_id == organization_id,
            ActionPlanMeasurement.campaign_id == campaign.id,
            ActionPlanMeasurement.business_location_id == location.id,
            ActionPlanMeasurement.measurement_status.in_(
                ("baseline_ready", "waiting_for_results", "measured")
            ),
        )
        .order_by(
            ActionPlanMeasurement.baseline_captured_at.asc(),
            ActionPlanMeasurement.id.asc(),
        )
        .all()
    )
    for measurement in rows:
        metric = _trustworthy_metric(measurement)
        if metric is None:
            continue
        contract = dict(measurement.measurement_contract or {})
        evidence = [
            {
                "evidence_type": "governed_baseline",
                "measurement_id": measurement.id,
                "business_location_id": location.id,
                "campaign_id": campaign.id,
                "metric_id": metric.get("metric_id"),
                "metric_value": metric.get("value"),
                "metric_unit": metric.get("unit"),
                "contract_version": contract.get("version"),
                "contract_track": contract.get("track"),
                "source_record_id": metric.get("source_record_id"),
                "captured_at": _iso(measurement.baseline_captured_at),
            }
        ]
        return EligibleAchievement(
            rule_key="foundation.first_trustworthy_baseline",
            category="foundation",
            title="Starting point saved",
            description="A measured starting point is saved so future work can be checked fairly.",
            qualified_at=_as_utc(measurement.baseline_captured_at),
            evidence=evidence,
        )
    return None


def _eligible_achievements(
    db: Session,
    *,
    organization_id: str,
    campaign: Campaign,
    location: BusinessLocation,
) -> list[EligibleAchievement]:
    candidates = (
        _location_ready(campaign, location),
        _first_live_sync(
            db,
            organization_id=organization_id,
            campaign=campaign,
            location=location,
        ),
        _first_trustworthy_baseline(
            db,
            organization_id=organization_id,
            campaign=campaign,
            location=location,
        ),
    )
    return [item for item in candidates if item is not None]


def _grant_achievement(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    location: BusinessLocation,
    eligible: EligibleAchievement,
) -> tuple[AchievementGrant, bool]:
    existing = (
        db.query(AchievementGrant)
        .filter(
            AchievementGrant.tenant_id == tenant_id,
            AchievementGrant.rule_key == eligible.rule_key,
            AchievementGrant.rule_version == RULE_VERSION,
            AchievementGrant.scope_type == "location",
            AchievementGrant.scope_id == location.id,
        )
        .first()
    )
    if existing is not None:
        return existing, False

    row = AchievementGrant(
        tenant_id=tenant_id,
        organization_id=organization_id,
        business_location_id=location.id,
        rule_key=eligible.rule_key,
        rule_version=RULE_VERSION,
        category=eligible.category,
        scope_type="location",
        scope_id=location.id,
        title=eligible.title,
        description=eligible.description,
        evidence=eligible.evidence,
        evidence_sha256=_evidence_digest(eligible.evidence),
        qualified_at=eligible.qualified_at,
        earned_at=datetime.now(UTC),
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        return row, True
    except IntegrityError:
        existing = (
            db.query(AchievementGrant)
            .filter(
                AchievementGrant.tenant_id == tenant_id,
                AchievementGrant.rule_key == eligible.rule_key,
                AchievementGrant.rule_version == RULE_VERSION,
                AchievementGrant.scope_type == "location",
                AchievementGrant.scope_id == location.id,
            )
            .one()
        )
        return existing, False


def _serialize_grant(row: AchievementGrant, *, location_name: str) -> dict[str, Any]:
    return {
        "id": row.id,
        "rule_key": row.rule_key,
        "rule_version": row.rule_version,
        "category": row.category,
        "scope": {
            "type": row.scope_type,
            "id": row.scope_id,
            "label": location_name,
        },
        "title": row.title,
        "description": row.description,
        "evidence": list(row.evidence or []),
        "qualified_at": _iso(row.qualified_at),
        "earned_at": _iso(row.earned_at),
        "corrected_at": _iso(row.corrected_at),
        "correction_reason": row.correction_reason,
    }


def _serialize_preference(row: AchievementPreference | None) -> dict[str, bool]:
    return {
        "celebrations_enabled": row.celebrations_enabled if row is not None else True,
        "notifications_enabled": row.notifications_enabled if row is not None else True,
    }


def _next_milestone(earned_keys: set[str]) -> dict[str, Any] | None:
    for position, rule in enumerate(FOUNDATION_RULES, start=1):
        if rule["rule_key"] in earned_keys:
            continue
        return {
            **rule,
            "category": "foundation",
            "position": position,
            "total": len(FOUNDATION_RULES),
        }
    return None


def achievement_summary(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    user_id: str,
    campaign_id: str,
    evaluate: bool,
) -> dict[str, Any]:
    campaign, location = _campaign_and_location(
        db,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    newly_earned: list[AchievementGrant] = []
    if evaluate:
        for eligible in _eligible_achievements(
            db,
            organization_id=organization_id,
            campaign=campaign,
            location=location,
        ):
            row, created = _grant_achievement(
                db,
                tenant_id=tenant_id,
                organization_id=organization_id,
                location=location,
                eligible=eligible,
            )
            if created:
                newly_earned.append(row)
        db.commit()
        for row in newly_earned:
            record_server_event_safely(
                db,
                tenant_id=tenant_id,
                organization_id=organization_id,
                actor_user_id=user_id,
                event_name="achievement.earned",
                campaign_id=campaign.id,
                properties={"category": row.category, "rule_key": row.rule_key},
                idempotency_key=f"achievement-earned:{row.id}",
            )

    grants = (
        db.query(AchievementGrant)
        .filter(
            AchievementGrant.tenant_id == tenant_id,
            AchievementGrant.organization_id == organization_id,
            AchievementGrant.business_location_id == location.id,
        )
        .order_by(AchievementGrant.earned_at.desc(), AchievementGrant.id.desc())
        .all()
    )
    preference = (
        db.query(AchievementPreference)
        .filter(
            AchievementPreference.tenant_id == tenant_id,
            AchievementPreference.user_id == user_id,
        )
        .first()
    )
    active = [row for row in grants if row.corrected_at is None]
    active_keys = {row.rule_key for row in active}
    foundation_earned_count = sum(1 for row in active if row.category == "foundation")
    return {
        "campaign_id": campaign.id,
        "business_location": {"id": location.id, "name": location.name},
        "earned_count": len(active),
        "foundation_earned_count": foundation_earned_count,
        "foundation_total": len(FOUNDATION_RULES),
        "newly_earned": [
            _serialize_grant(row, location_name=location.name) for row in newly_earned
        ],
        "achievements": [
            _serialize_grant(row, location_name=location.name) for row in grants
        ],
        "next_milestone": _next_milestone(active_keys),
        "preferences": _serialize_preference(preference),
        "safety": {
            "verified_result_rewards_enabled": False,
            "message": "Improvement rewards stay locked until fresh measurements prove the result.",
        },
    }


def update_preferences(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    user_id: str,
    celebrations_enabled: bool | None,
    notifications_enabled: bool | None,
) -> dict[str, bool]:
    row = (
        db.query(AchievementPreference)
        .filter(
            AchievementPreference.tenant_id == tenant_id,
            AchievementPreference.user_id == user_id,
        )
        .first()
    )
    if row is None:
        row = AchievementPreference(
            tenant_id=tenant_id,
            organization_id=organization_id,
            user_id=user_id,
            celebrations_enabled=(
                celebrations_enabled if celebrations_enabled is not None else True
            ),
            notifications_enabled=(
                notifications_enabled if notifications_enabled is not None else True
            ),
        )
        db.add(row)
    else:
        if celebrations_enabled is not None:
            row.celebrations_enabled = celebrations_enabled
        if notifications_enabled is not None:
            row.notifications_enabled = notifications_enabled
    row.updated_at = datetime.now(UTC)
    db.commit()
    return _serialize_preference(row)
