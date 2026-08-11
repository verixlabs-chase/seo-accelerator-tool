from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.organization import Organization
from app.models.product_analytics import ProductAnalyticsEvent, ProductFeedback


class ProductAnalyticsError(ValueError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


@dataclass(frozen=True)
class ProductEventSpec:
    event_name: str
    category: str
    owner: str
    purpose: str
    schema_version: str
    retention_days: int
    allowed_properties: dict[str, frozenset[str]]
    required_properties: frozenset[str] = frozenset()
    instrumentation_status: str = "planned"
    client_recordable: bool = False


logger = logging.getLogger(__name__)


GLOBAL_PROHIBITED_FIELDS = (
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "secret",
    "api_key",
    "email",
    "phone",
    "url",
    "page_content",
    "page_text",
    "prompt",
    "response",
    "review_text",
    "search_query",
    "keyword",
    "provider_payload",
)


def _values(*items: str) -> frozenset[str]:
    return frozenset(items)


EVENT_SPECS: dict[str, ProductEventSpec] = {
    spec.event_name: spec
    for spec in (
        ProductEventSpec(
            "onboarding.started",
            "activation",
            "customer-experience",
            "Find where customers begin guided setup.",
            "1.0",
            400,
            {"entry_point": _values("workspace_setup", "empty_dashboard")},
            frozenset({"entry_point"}),
            "active",
            True,
        ),
        ProductEventSpec(
            "onboarding.completed",
            "activation",
            "customer-experience",
            "Measure completed setup and partial setup outcomes.",
            "1.0",
            400,
            {"result_status": _values("success", "partial")},
            frozenset({"result_status"}),
            "active",
            True,
        ),
        ProductEventSpec(
            "connection.connected",
            "activation",
            "data-connections",
            "Measure when a governed data connection becomes usable.",
            "1.0",
            400,
            {"connection_kind": _values("search_console", "analytics", "business_profile")},
        ),
        ProductEventSpec(
            "value.first_verified_insight",
            "value",
            "intelligence",
            "Measure the first recommendation backed by saved evidence.",
            "1.0",
            730,
            {"value_kind": _values("recommendation_with_evidence")},
            frozenset({"value_kind"}),
            "active",
        ),
        ProductEventSpec(
            "workspace.location_switched",
            "engagement",
            "multi-location",
            "Measure whether customers can move between locations.",
            "1.0",
            180,
            {"selection_origin": _values("top_bar")},
            frozenset({"selection_origin"}),
            "active",
            True,
        ),
        ProductEventSpec(
            "recommendation.viewed",
            "recommendations",
            "intelligence",
            "Measure whether customers open a recommended action.",
            "1.0",
            400,
            {"surface": _values("next_steps")},
            frozenset({"surface"}),
            "active",
            True,
        ),
        ProductEventSpec(
            "recommendation.approved",
            "recommendations",
            "intelligence",
            "Measure deliberate recommendation acceptance.",
            "1.0",
            730,
            {"surface": _values("next_steps", "execution_review")},
        ),
        ProductEventSpec(
            "recommendation.rejected",
            "recommendations",
            "intelligence",
            "Measure deliberate recommendation rejection.",
            "1.0",
            730,
            {"surface": _values("next_steps", "execution_review")},
        ),
        ProductEventSpec(
            "action.step_completed",
            "actions",
            "intelligence",
            "Measure meaningful checklist follow-through.",
            "1.0",
            730,
            {"surface": _values("next_steps")},
            frozenset({"surface"}),
            "active",
        ),
        ProductEventSpec(
            "action.outcome_available",
            "outcomes",
            "measurement",
            "Measure when completed work receives an honest result.",
            "1.0",
            730,
            {
                "result_direction": _values(
                    "improved", "declined", "unchanged", "inconclusive"
                )
            },
            frozenset({"result_direction"}),
            "active",
        ),
        ProductEventSpec(
            "forecast.viewed",
            "forecasting",
            "measurement",
            "Measure exposure to a forecast with a saved starting point.",
            "1.0",
            400,
            {"data_quality": _values("strong", "partial")},
            frozenset({"data_quality"}),
            "active",
            True,
        ),
        ProductEventSpec(
            "report.viewed",
            "reporting",
            "reporting",
            "Measure report engagement without tracking recipients or report contents.",
            "1.0",
            400,
            {"report_kind": _values("monthly", "on_demand")},
        ),
        ProductEventSpec(
            "notification.opened",
            "notifications",
            "customer-experience",
            "Measure whether meaningful alerts bring customers back.",
            "1.0",
            180,
            {"notification_kind": _values("alert", "digest", "connection_failure")},
        ),
        ProductEventSpec(
            "help.opened",
            "support",
            "customer-experience",
            "Find screens that require additional explanation.",
            "1.0",
            180,
            {"surface": _values("dashboard", "next_steps", "settings", "reports")},
        ),
        ProductEventSpec(
            "support.escalated",
            "support",
            "customer-experience",
            "Measure setup and product paths that require human help.",
            "1.0",
            400,
            {"reason": _values("setup_blocked", "connection_blocked", "product_question")},
        ),
        ProductEventSpec(
            "automation.completed",
            "automation",
            "automation",
            "Measure successful governed automation without exporting action contents.",
            "1.0",
            730,
            {"automation_kind": _values("wordpress", "business_profile", "webhook")},
        ),
    )
}

FEEDBACK_CONTEXTS = {
    "recommendation_usefulness",
    "explanation_clarity",
    "forecast_trust",
    "automation_confidence",
    "report_quality",
}
FEEDBACK_REASONS = {
    "useful",
    "clear",
    "believable",
    "not_useful_yet",
    "unclear",
    "missing_context",
    "too_technical",
    "not_believable",
}
FEEDBACK_SUBJECT_BY_CONTEXT = {
    "recommendation_usefulness": "recommendation",
    "explanation_clarity": "explanation",
    "forecast_trust": "forecast",
    "automation_confidence": "automation",
    "report_quality": "report",
}
USEFUL_EVENT_NAMES = {
    "value.first_verified_insight",
    "recommendation.approved",
    "action.step_completed",
    "action.outcome_available",
    "report.viewed",
    "automation.completed",
}


def _normalize_timestamp(value: datetime | None) -> datetime:
    now = datetime.now(UTC)
    if value is None:
        return now
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    if normalized > now + timedelta(minutes=5) or normalized < now - timedelta(days=7):
        raise ProductAnalyticsError(
            "The event time is outside the accepted window.",
            reason_code="event_time_out_of_range",
        )
    return normalized


def _validate_campaign(db: Session, *, organization_id: str, campaign_id: str | None) -> None:
    if campaign_id is None:
        return
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).one_or_none()
    if campaign is None:
        raise ProductAnalyticsError(
            "The selected business could not be found.",
            reason_code="campaign_not_found",
            status_code=404,
        )
    if campaign.organization_id != organization_id:
        raise ProductAnalyticsError(
            "The selected business does not belong to this organization.",
            reason_code="organization_scope_mismatch",
            status_code=403,
        )


def _validate_properties(spec: ProductEventSpec, properties: dict[str, Any]) -> dict[str, str]:
    lowered = {str(key).strip().lower() for key in properties}
    prohibited = sorted(lowered.intersection(GLOBAL_PROHIBITED_FIELDS))
    if prohibited:
        raise ProductAnalyticsError(
            "Sensitive or business-content fields cannot be recorded.",
            reason_code="prohibited_analytics_field",
        )
    unexpected = sorted(set(properties).difference(spec.allowed_properties))
    if unexpected:
        raise ProductAnalyticsError(
            "This event contains fields that are not in its governed schema.",
            reason_code="analytics_schema_violation",
        )
    missing = sorted(spec.required_properties.difference(properties))
    if missing:
        raise ProductAnalyticsError(
            "This event is missing a required governed field.",
            reason_code="analytics_schema_violation",
        )
    normalized: dict[str, str] = {}
    for key, raw_value in properties.items():
        if not isinstance(raw_value, str):
            raise ProductAnalyticsError(
                "Analytics properties must use short governed labels.",
                reason_code="analytics_schema_violation",
            )
        value = raw_value.strip().lower()
        if value not in spec.allowed_properties[key]:
            raise ProductAnalyticsError(
                "An analytics property value is outside its governed schema.",
                reason_code="analytics_schema_violation",
            )
        normalized[key] = value
    return normalized


def _is_synthetic_organization(organization: Organization) -> bool:
    return (
        organization.plan_type == "internal_anchor"
        or organization.billing_mode == "platform_sponsored"
    )


def record_event(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    actor_user_id: str | None,
    event_name: str,
    campaign_id: str | None,
    properties: dict[str, Any],
    occurred_at: datetime | None = None,
    idempotency_key: str | None = None,
    source: str = "product_client",
    is_synthetic: bool = False,
) -> tuple[ProductAnalyticsEvent, bool]:
    spec = EVENT_SPECS.get(event_name)
    if spec is None:
        raise ProductAnalyticsError(
            "This product event is not registered.",
            reason_code="unknown_product_event",
        )
    if spec.instrumentation_status != "active" and source == "product_client":
        raise ProductAnalyticsError(
            "This product event is not active yet.",
            reason_code="product_event_not_active",
        )
    if source == "product_client" and not spec.client_recordable:
        raise ProductAnalyticsError(
            "This event requires verified server evidence.",
            reason_code="event_requires_server_evidence",
        )
    _validate_campaign(db, organization_id=organization_id, campaign_id=campaign_id)
    normalized_properties = _validate_properties(spec, properties)
    organization = db.query(Organization).filter(Organization.id == organization_id).one_or_none()
    if organization is None:
        raise ProductAnalyticsError(
            "The organization could not be found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    if idempotency_key:
        existing = (
            db.query(ProductAnalyticsEvent)
            .filter(
                ProductAnalyticsEvent.organization_id == organization_id,
                ProductAnalyticsEvent.idempotency_key == idempotency_key,
            )
            .one_or_none()
        )
        if existing is not None:
            return existing, False
    row = ProductAnalyticsEvent(
        tenant_id=tenant_id,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        campaign_id=campaign_id,
        event_name=event_name,
        category=spec.category,
        schema_version=spec.schema_version,
        plan_type=organization.plan_type,
        source=source,
        properties_json=normalized_properties,
        idempotency_key=idempotency_key,
        is_synthetic=is_synthetic or _is_synthetic_organization(organization),
        occurred_at=_normalize_timestamp(occurred_at),
        received_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()
    return row, True


def record_server_event_safely(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    actor_user_id: str | None,
    event_name: str,
    campaign_id: str | None,
    properties: dict[str, Any],
    idempotency_key: str,
) -> bool:
    """Persist trusted measurement without interrupting the customer's work."""

    try:
        _row, created = record_event(
            db,
            tenant_id=tenant_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            event_name=event_name,
            campaign_id=campaign_id,
            properties=properties,
            idempotency_key=idempotency_key,
            source="product_server",
        )
        db.commit()
        return created
    except Exception:  # noqa: BLE001 - analytics must not break a verified product action
        db.rollback()
        logger.warning("Unable to record governed product event %s", event_name, exc_info=True)
        return False


def record_feedback(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    actor_user_id: str | None,
    campaign_id: str | None,
    context: str,
    subject_type: str,
    subject_id: str | None,
    rating: int,
    reason_code: str,
) -> ProductFeedback:
    if (
        context not in FEEDBACK_CONTEXTS
        or reason_code not in FEEDBACK_REASONS
        or FEEDBACK_SUBJECT_BY_CONTEXT.get(context) != subject_type
    ):
        raise ProductAnalyticsError(
            "Feedback does not match the governed feedback contract.",
            reason_code="feedback_schema_violation",
        )
    _validate_campaign(db, organization_id=organization_id, campaign_id=campaign_id)
    organization = db.query(Organization).filter(Organization.id == organization_id).one_or_none()
    if organization is None:
        raise ProductAnalyticsError(
            "The organization could not be found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    row = ProductFeedback(
        tenant_id=tenant_id,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        campaign_id=campaign_id,
        context=context,
        subject_type=subject_type,
        subject_id=subject_id,
        rating=rating,
        reason_code=reason_code,
        plan_type=organization.plan_type,
        is_synthetic=_is_synthetic_organization(organization),
    )
    db.add(row)
    db.flush()
    return row


def serialize_event(row: ProductAnalyticsEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "event_name": row.event_name,
        "schema_version": row.schema_version,
        "recorded": True,
        "occurred_at": row.occurred_at.isoformat(),
    }


def taxonomy_summary() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "autocapture_enabled": False,
        "session_replay_enabled": False,
        "prohibited_sensitive_fields": list(GLOBAL_PROHIBITED_FIELDS),
        "events": [
            {
                "event_name": spec.event_name,
                "category": spec.category,
                "owner": spec.owner,
                "purpose": spec.purpose,
                "schema_version": spec.schema_version,
                "retention_days": spec.retention_days,
                "allowed_properties": sorted(spec.allowed_properties),
                "required_properties": sorted(spec.required_properties),
                "instrumentation_status": spec.instrumentation_status,
                "client_recordable": spec.client_recordable,
            }
            for spec in EVENT_SPECS.values()
        ],
    }


def _rate(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 1) if denominator else 0.0


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def build_value_summary(db: Session, *, days: int) -> dict[str, Any]:
    now = datetime.now(UTC)
    start = now - timedelta(days=days)
    active_orgs = [
        row
        for row in db.query(Organization).filter(Organization.status == "active").all()
        if not _is_synthetic_organization(row)
    ]
    events = (
        db.query(ProductAnalyticsEvent)
        .filter(ProductAnalyticsEvent.occurred_at >= start)
        .order_by(ProductAnalyticsEvent.occurred_at.asc())
        .all()
    )
    feedback_rows = (
        db.query(ProductFeedback)
        .filter(ProductFeedback.created_at >= start)
        .order_by(ProductFeedback.created_at.asc())
        .all()
    )
    synthetic_excluded = sum(1 for row in events if row.is_synthetic)
    synthetic_feedback_excluded = sum(1 for row in feedback_rows if row.is_synthetic)
    real_events = [row for row in events if not row.is_synthetic]
    real_feedback = [row for row in feedback_rows if not row.is_synthetic]
    event_names_by_org: dict[str, set[str]] = defaultdict(set)
    useful_weeks_by_org: dict[str, set[tuple[int, int]]] = defaultdict(set)
    first_event_by_org_name: dict[tuple[str, str], datetime] = {}
    for row in real_events:
        occurred_at = _as_utc(row.occurred_at)
        event_names_by_org[row.organization_id].add(row.event_name)
        key = (row.organization_id, row.event_name)
        first_event_by_org_name.setdefault(key, occurred_at)
        if row.event_name in USEFUL_EVENT_NAMES:
            iso = occurred_at.isocalendar()
            useful_weeks_by_org[row.organization_id].add((iso.year, iso.week))

    activated_orgs = {
        org_id for org_id, names in event_names_by_org.items() if "onboarding.completed" in names
    }
    first_value_orgs = {
        org_id
        for org_id, names in event_names_by_org.items()
        if "value.first_verified_insight" in names
    }
    action_orgs = {
        org_id for org_id, names in event_names_by_org.items() if "action.step_completed" in names
    }
    repeated_value_orgs = {
        org_id for org_id, weeks in useful_weeks_by_org.items() if len(weeks) >= 2
    }
    recent_cutoff = now - timedelta(days=14)
    recently_useful_orgs = {
        row.organization_id
        for row in real_events
        if row.event_name in USEFUL_EVENT_NAMES and _as_utc(row.occurred_at) >= recent_cutoff
    }
    needs_attention_orgs = first_value_orgs.difference(recently_useful_orgs)
    time_to_value: list[float] = []
    for org_id in first_value_orgs:
        started = first_event_by_org_name.get((org_id, "onboarding.started"))
        valued = first_event_by_org_name.get((org_id, "value.first_verified_insight"))
        if started and valued and valued >= started:
            time_to_value.append((valued - started).total_seconds() / 3600)

    all_plan_types = sorted({org.plan_type for org in active_orgs}.union(row.plan_type for row in real_events))
    cohorts: list[dict[str, Any]] = []
    for plan_type in all_plan_types:
        eligible = {org.id for org in active_orgs if org.plan_type == plan_type}
        cohorts.append(
            {
                "plan_type": plan_type,
                "eligible_organizations": len(eligible),
                "activated": len(eligible.intersection(activated_orgs)),
                "first_value": len(eligible.intersection(first_value_orgs)),
                "action_completed": len(eligible.intersection(action_orgs)),
                "repeated_value": len(eligible.intersection(repeated_value_orgs)),
            }
        )

    feedback_by_context: dict[str, list[int]] = defaultdict(list)
    for row in real_feedback:
        feedback_by_context[row.context].append(row.rating)
    feedback = [
        {
            "context": context,
            "responses": len(ratings),
            "average_rating": round(mean(ratings), 2),
            "positive_rate": _rate(sum(1 for rating in ratings if rating >= 4), len(ratings)),
        }
        for context, ratings in sorted(feedback_by_context.items())
    ]

    counts_by_name: dict[str, int] = defaultdict(int)
    for row in real_events:
        counts_by_name[row.event_name] += 1
    coverage = [
        {
            "event_name": spec.event_name,
            "owner": spec.owner,
            "instrumentation_status": spec.instrumentation_status,
            "events_in_period": counts_by_name.get(spec.event_name, 0),
            "coverage_state": (
                "planned"
                if spec.instrumentation_status != "active"
                else "active"
                if counts_by_name.get(spec.event_name, 0) > 0
                else "active_no_recent_events"
            ),
        }
        for spec in EVENT_SPECS.values()
    ]
    eligible_count = len(active_orgs)
    return {
        "period": {
            "days": days,
            "start": start.isoformat(),
            "end": now.isoformat(),
        },
        "privacy": {
            "aggregate_only": True,
            "autocapture_enabled": False,
            "session_replay_enabled": False,
            "synthetic_events_excluded": synthetic_excluded,
            "synthetic_feedback_excluded": synthetic_feedback_excluded,
        },
        "funnel": {
            "eligible_organizations": eligible_count,
            "activated": len(activated_orgs),
            "activation_rate": _rate(len(activated_orgs), eligible_count),
            "first_value": len(first_value_orgs),
            "first_value_rate": _rate(len(first_value_orgs), eligible_count),
            "action_completed": len(action_orgs),
            "action_completion_rate": _rate(len(action_orgs), eligible_count),
            "repeated_value": len(repeated_value_orgs),
            "repeated_value_rate": _rate(len(repeated_value_orgs), eligible_count),
            "needs_attention": len(needs_attention_orgs),
            "average_hours_to_first_value": (
                round(mean(time_to_value), 2) if time_to_value else None
            ),
            "time_to_first_value_samples": len(time_to_value),
        },
        "cohorts": cohorts,
        "feedback": feedback,
        "instrumentation": {
            "registered_events": len(EVENT_SPECS),
            "active_events": sum(
                1 for spec in EVENT_SPECS.values() if spec.instrumentation_status == "active"
            ),
            "coverage": coverage,
        },
    }
