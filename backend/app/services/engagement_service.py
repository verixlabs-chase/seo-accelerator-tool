from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.action_plan import ActionPlanMeasurement, ActionPlanOccurrence, ActionPlanStep
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

HABIT_RULES = (
    {
        "rule_key": "habit.first_weekly_plan",
        "title": "Weekly plan completed",
        "description": "Every required step in one weekly plan was finished.",
    },
    {
        "rule_key": "habit.three_weekly_plans",
        "title": "Three weeks of follow-through",
        "description": "Weekly plans were completed in three different work periods.",
    },
    {
        "rule_key": "habit.first_monthly_plan",
        "title": "Monthly check-in completed",
        "description": "Every required step in one monthly plan was finished.",
    },
)

MULTI_LOCATION_RULES = (
    {
        "rule_key": "multi_location.all_locations_ready",
        "title": "Every location is ready",
        "description": "Every active location has the basic business details needed for measurement.",
    },
    {
        "rule_key": "multi_location.all_locations_current",
        "title": "Every location is reporting",
        "description": "Every active location received a successful data update during the freshness window.",
    },
)

PORTFOLIO_FRESHNESS_DAYS = 21


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


def _completed_plan_occurrences(
    db: Session,
    *,
    organization_id: str,
    campaign: Campaign,
    location: BusinessLocation,
    cadence: str,
) -> list[tuple[ActionPlanOccurrence, list[ActionPlanStep]]]:
    rows = (
        db.query(ActionPlanOccurrence)
        .filter(
            ActionPlanOccurrence.organization_id == organization_id,
            ActionPlanOccurrence.campaign_id == campaign.id,
            ActionPlanOccurrence.business_location_id == location.id,
            ActionPlanOccurrence.cadence == cadence,
            ActionPlanOccurrence.status.in_(("waiting_for_results", "completed")),
            ActionPlanOccurrence.completed_at.is_not(None),
        )
        .order_by(
            ActionPlanOccurrence.completed_at.asc(),
            ActionPlanOccurrence.id.asc(),
        )
        .all()
    )
    completed: list[tuple[ActionPlanOccurrence, list[ActionPlanStep]]] = []
    for occurrence in rows:
        required_steps = (
            db.query(ActionPlanStep)
            .filter(
                ActionPlanStep.organization_id == organization_id,
                ActionPlanStep.occurrence_id == occurrence.id,
                ActionPlanStep.required.is_(True),
            )
            .order_by(ActionPlanStep.position.asc(), ActionPlanStep.id.asc())
            .all()
        )
        if not required_steps or any(step.status != "done" for step in required_steps):
            continue
        completed.append((occurrence, required_steps))
    return completed


def _checklist_evidence(
    occurrence: ActionPlanOccurrence,
    required_steps: list[ActionPlanStep],
) -> dict[str, Any]:
    return {
        "evidence_type": "checklist_completion",
        "occurrence_id": occurrence.id,
        "campaign_id": occurrence.campaign_id,
        "business_location_id": occurrence.business_location_id,
        "cadence": occurrence.cadence,
        "period_key": occurrence.period_key,
        "action_id": occurrence.action_id,
        "required_steps_completed": len(required_steps),
        "completed_at": _iso(occurrence.completed_at),
    }


def _habit_achievements(
    db: Session,
    *,
    organization_id: str,
    campaign: Campaign,
    location: BusinessLocation,
) -> list[EligibleAchievement]:
    weekly = _completed_plan_occurrences(
        db,
        organization_id=organization_id,
        campaign=campaign,
        location=location,
        cadence="weekly",
    )
    monthly = _completed_plan_occurrences(
        db,
        organization_id=organization_id,
        campaign=campaign,
        location=location,
        cadence="monthly",
    )
    eligible: list[EligibleAchievement] = []
    if weekly:
        occurrence, steps = weekly[0]
        eligible.append(
            EligibleAchievement(
                rule_key="habit.first_weekly_plan",
                category="habit",
                title="Weekly plan completed",
                description="Every required step in one weekly plan was finished.",
                qualified_at=_as_utc(occurrence.completed_at),
                evidence=[_checklist_evidence(occurrence, steps)],
            )
        )

    distinct_weekly: list[tuple[ActionPlanOccurrence, list[ActionPlanStep]]] = []
    seen_periods: set[str] = set()
    for occurrence, steps in weekly:
        if occurrence.period_key in seen_periods:
            continue
        seen_periods.add(occurrence.period_key)
        distinct_weekly.append((occurrence, steps))
    if len(distinct_weekly) >= 3:
        qualifying = distinct_weekly[:3]
        eligible.append(
            EligibleAchievement(
                rule_key="habit.three_weekly_plans",
                category="habit",
                title="Three weeks of follow-through",
                description="Weekly plans were completed in three different work periods.",
                qualified_at=max(_as_utc(item[0].completed_at) for item in qualifying),
                evidence=[
                    _checklist_evidence(occurrence, steps)
                    for occurrence, steps in qualifying
                ],
            )
        )

    if monthly:
        occurrence, steps = monthly[0]
        eligible.append(
            EligibleAchievement(
                rule_key="habit.first_monthly_plan",
                category="habit",
                title="Monthly check-in completed",
                description="Every required step in one monthly plan was finished.",
                qualified_at=_as_utc(occurrence.completed_at),
                evidence=[_checklist_evidence(occurrence, steps)],
            )
        )
    return eligible


def _active_locations(db: Session, *, organization_id: str) -> list[BusinessLocation]:
    return (
        db.query(BusinessLocation)
        .filter(
            BusinessLocation.organization_id == organization_id,
            BusinessLocation.status == "active",
        )
        .order_by(BusinessLocation.name.asc(), BusinessLocation.id.asc())
        .all()
    )


def _all_locations_ready(
    locations: list[BusinessLocation],
) -> EligibleAchievement | None:
    if len(locations) < 2:
        return None
    location_evidence: list[dict[str, Any]] = []
    qualified_times: list[datetime] = []
    for location in locations:
        domain = (location.domain or "").strip()
        service_area = (
            location.city
            or location.primary_city
            or location.postal_code
            or location.region
            or ""
        ).strip()
        if not location.name.strip() or not domain or not service_area:
            return None
        qualified_times.append(_as_utc(location.updated_at or location.created_at))
        location_evidence.append(
            {
                "business_location_id": location.id,
                "location_name": location.name,
                "website": domain,
                "service_area": service_area,
            }
        )
    return EligibleAchievement(
        rule_key="multi_location.all_locations_ready",
        category="multi_location",
        title="Every location is ready",
        description="Every active location has the basic business details needed for measurement.",
        qualified_at=max(qualified_times),
        evidence=[
            {
                "evidence_type": "portfolio_location_setup",
                "active_location_count": len(locations),
                "locations": location_evidence,
            }
        ],
    )


def _all_locations_current(
    db: Session,
    *,
    organization_id: str,
    locations: list[BusinessLocation],
    evaluated_at: datetime,
) -> EligibleAchievement | None:
    if len(locations) < 2:
        return None
    cutoff = evaluated_at - timedelta(days=PORTFOLIO_FRESHNESS_DAYS)
    update_evidence: list[dict[str, Any]] = []
    successful_times: list[datetime] = []
    for location in locations:
        connection = (
            db.query(DataConnection)
            .filter(
                DataConnection.organization_id == organization_id,
                DataConnection.business_location_id == location.id,
                DataConnection.provider_name.in_(SUPPORTED_LIVE_PROVIDERS),
                DataConnection.status == "connected",
                DataConnection.last_success_at.is_not(None),
                DataConnection.last_success_at >= cutoff,
            )
            .order_by(DataConnection.last_success_at.desc(), DataConnection.id.asc())
            .first()
        )
        if connection is None or connection.last_success_at is None:
            return None
        successful_at = _as_utc(connection.last_success_at)
        successful_times.append(successful_at)
        update_evidence.append(
            {
                "business_location_id": location.id,
                "location_name": location.name,
                "connection_id": connection.id,
                "successful_at": successful_at.isoformat(),
            }
        )
    return EligibleAchievement(
        rule_key="multi_location.all_locations_current",
        category="multi_location",
        title="Every location is reporting",
        description="Every active location received a successful data update during the freshness window.",
        qualified_at=max(successful_times),
        evidence=[
            {
                "evidence_type": "portfolio_data_current",
                "active_location_count": len(locations),
                "freshness_window_days": PORTFOLIO_FRESHNESS_DAYS,
                "evaluated_at": evaluated_at.isoformat(),
                "locations": update_evidence,
            }
        ],
    )


def _eligible_organization_achievements(
    db: Session,
    *,
    organization_id: str,
) -> tuple[list[EligibleAchievement], int]:
    locations = _active_locations(db, organization_id=organization_id)
    evaluated_at = datetime.now(UTC)
    candidates = (
        _all_locations_ready(locations),
        _all_locations_current(
            db,
            organization_id=organization_id,
            locations=locations,
            evaluated_at=evaluated_at,
        ),
    )
    return [item for item in candidates if item is not None], len(locations)


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
    return [item for item in candidates if item is not None] + _habit_achievements(
        db,
        organization_id=organization_id,
        campaign=campaign,
        location=location,
    )


def _grant_achievement(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    scope_type: str,
    scope_id: str,
    business_location_id: str | None,
    eligible: EligibleAchievement,
) -> tuple[AchievementGrant, bool]:
    existing = (
        db.query(AchievementGrant)
        .filter(
            AchievementGrant.tenant_id == tenant_id,
            AchievementGrant.rule_key == eligible.rule_key,
            AchievementGrant.rule_version == RULE_VERSION,
            AchievementGrant.scope_type == scope_type,
            AchievementGrant.scope_id == scope_id,
        )
        .first()
    )
    if existing is not None:
        return existing, False

    row = AchievementGrant(
        tenant_id=tenant_id,
        organization_id=organization_id,
        business_location_id=business_location_id,
        rule_key=eligible.rule_key,
        rule_version=RULE_VERSION,
        category=eligible.category,
        scope_type=scope_type,
        scope_id=scope_id,
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
                AchievementGrant.scope_type == scope_type,
                AchievementGrant.scope_id == scope_id,
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
            "label": (
                "All active locations"
                if row.scope_type == "organization"
                else location_name
            ),
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


def _next_milestone(
    earned_keys: set[str],
    *,
    include_multi_location: bool,
) -> dict[str, Any] | None:
    rules = FOUNDATION_RULES + HABIT_RULES
    if include_multi_location:
        rules += MULTI_LOCATION_RULES
    for position, rule in enumerate(rules, start=1):
        if rule["rule_key"] in earned_keys:
            continue
        return {
            **rule,
            "category": (
                "foundation"
                if rule["rule_key"].startswith("foundation.")
                else "habit"
                if rule["rule_key"].startswith("habit.")
                else "multi_location"
            ),
            "position": position,
            "total": len(rules),
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
    organization_eligible, active_location_count = _eligible_organization_achievements(
        db,
        organization_id=organization_id,
    )
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
                scope_type="location",
                scope_id=location.id,
                business_location_id=location.id,
                eligible=eligible,
            )
            if created:
                newly_earned.append(row)
        for eligible in organization_eligible:
            row, created = _grant_achievement(
                db,
                tenant_id=tenant_id,
                organization_id=organization_id,
                scope_type="organization",
                scope_id=organization_id,
                business_location_id=None,
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
            or_(
                AchievementGrant.business_location_id == location.id,
                and_(
                    AchievementGrant.scope_type == "organization",
                    AchievementGrant.scope_id == organization_id,
                ),
            ),
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
    habit_earned_count = sum(1 for row in active if row.category == "habit")
    multi_location_earned_count = sum(
        1 for row in active if row.category == "multi_location"
    )
    progress_total = len(FOUNDATION_RULES) + len(HABIT_RULES)
    if active_location_count >= 2:
        progress_total += len(MULTI_LOCATION_RULES)
    return {
        "campaign_id": campaign.id,
        "business_location": {"id": location.id, "name": location.name},
        "earned_count": len(active),
        "foundation_earned_count": foundation_earned_count,
        "foundation_total": len(FOUNDATION_RULES),
        "habit_earned_count": habit_earned_count,
        "habit_total": len(HABIT_RULES),
        "multi_location_earned_count": multi_location_earned_count,
        "multi_location_total": (
            len(MULTI_LOCATION_RULES) if active_location_count >= 2 else 0
        ),
        "progress_earned_count": (
            foundation_earned_count + habit_earned_count + multi_location_earned_count
        ),
        "progress_total": progress_total,
        "newly_earned": [
            _serialize_grant(row, location_name=location.name) for row in newly_earned
        ],
        "achievements": [
            _serialize_grant(row, location_name=location.name) for row in grants
        ],
        "next_milestone": _next_milestone(
            active_keys,
            include_multi_location=active_location_count >= 2,
        ),
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
