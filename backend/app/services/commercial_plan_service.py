from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any

from sqlalchemy.orm import Session

from app.domain.commercial_tiers import (
    COMMERCIAL_LEGACY_TIER_VERSION,
    COMMERCIAL_TIERS,
    commercial_entitlement_template,
    legacy_tier_code_for_plan,
    normalize_commercial_plan_code,
)
from app.domain.entitlement_codes import LIMIT_ACTIVE_LOCATIONS
from app.models.entitlement import Entitlement, EntitlementResetPeriod, EntitlementValueType
from app.models.organization import Organization
from app.models.tier_profile import TierProfile
from app.services.cost_economics_service import CostEconomicsError, resolve_plan_economics
from app.services.location_allowance_service import (
    ActiveLocationAllowanceError,
    get_active_location_allowance,
    lock_organization_for_location_allowance,
    validate_canonical_bridge_entitlement,
)
from app.services.provisioning_service import (
    TierProfileValidationError,
    validate_commercial_profile_pointer,
)


PLAN_CATALOG_VERSION = "commercial-plans-2026-08-v2"

FEATURE_WORDPRESS_EXECUTION = "wordpress_execution"
FEATURE_PROFILE_FLEET_ACTIONS = "business_profile_fleet_actions"
FEATURE_AUTOMATIC_REVIEW_REPLIES = "automatic_review_replies"
FEATURE_LISTING_CORRECTION_SYNC = "listing_correction_sync"
FEATURE_EXTERNAL_AUTOMATION = "external_automation"
FEATURE_PRIVATE_AI_PROVIDER = "private_ai_provider"
FEATURE_PERFORMANCE_TREND = "performance_trend"
FEATURE_CAMPAIGN_REPORT = "campaign_report"
FEATURE_CAMPAIGN_STRATEGY = "campaign_strategy"

_PLAN_LEVEL = {
    "solo": 1,
    "multi_location": 2,
    "enterprise": 3,
}

@dataclass(frozen=True)
class CommercialFeature:
    code: str
    label: str
    summary: str
    minimum_plan_code: str


FEATURES: tuple[CommercialFeature, ...] = (
    CommercialFeature(
        code="guided_search_plan",
        label="Search guidance and reports",
        summary="See what changed, what matters, and what to work on next.",
        minimum_plan_code="solo",
    ),
    CommercialFeature(
        code="keyword_research",
        label="Customer search research",
        summary="Find and track searches that match the work your business wants.",
        minimum_plan_code="solo",
    ),
    CommercialFeature(
        code=FEATURE_PERFORMANCE_TREND,
        label="Performance trends",
        summary="Compare saved business results over time without losing the underlying dates.",
        minimum_plan_code="solo",
    ),
    CommercialFeature(
        code=FEATURE_CAMPAIGN_REPORT,
        label="Owner-ready reports",
        summary="Create a clear report from saved results, completed work, and measured changes.",
        minimum_plan_code="solo",
    ),
    CommercialFeature(
        code=FEATURE_CAMPAIGN_STRATEGY,
        label="Deeper action plans",
        summary="Turn saved evidence into a deeper, policy-controlled plan for the next work cycle.",
        minimum_plan_code="multi_location",
    ),
    CommercialFeature(
        code=FEATURE_WORDPRESS_EXECUTION,
        label="WordPress changes",
        summary="Approve changes to website titles, descriptions, content, and other supported fields.",
        minimum_plan_code="multi_location",
    ),
    CommercialFeature(
        code=FEATURE_PROFILE_FLEET_ACTIONS,
        label="Bulk business profile work",
        summary="Prepare and manage approved profile work across several locations.",
        minimum_plan_code="multi_location",
    ),
    CommercialFeature(
        code=FEATURE_AUTOMATIC_REVIEW_REPLIES,
        label="Approved automatic review replies",
        summary="Use saved rules and approval controls to prepare or publish review replies.",
        minimum_plan_code="multi_location",
    ),
    CommercialFeature(
        code=FEATURE_LISTING_CORRECTION_SYNC,
        label="Managed directory corrections",
        summary="Prepare, submit, and monitor approved directory listing corrections.",
        minimum_plan_code="multi_location",
    ),
    CommercialFeature(
        code=FEATURE_EXTERNAL_AUTOMATION,
        label="External automation connections",
        summary="Connect approved workflow tools through governed events and actions.",
        minimum_plan_code="enterprise",
    ),
    CommercialFeature(
        code=FEATURE_PRIVATE_AI_PROVIDER,
        label="Private or local AI provider",
        summary="Use an approved private model endpoint with organization-level controls.",
        minimum_plan_code="enterprise",
    ),
)


class CommercialPlanFeatureDenied(CostEconomicsError):
    def __init__(
        self,
        *,
        feature: CommercialFeature,
        current_plan_name: str,
        required_plan_name: str,
    ) -> None:
        super().__init__(
            (
                f"{feature.label} is included with the {required_plan_name} plan. "
                f"Your {current_plan_name} plan and saved data remain unchanged."
            ),
            reason_code=f"{feature.code}_upgrade_required",
            status_code=403,
        )
        self.feature_code = feature.code
        self.required_plan_name = required_plan_name


class CommercialPlanMaterializationError(CostEconomicsError):
    def __init__(self, message: str, *, reason_code: str = "commercial_plan_materialization_failed") -> None:
        super().__init__(message, reason_code=reason_code, status_code=409)


def require_commercial_feature(
    db: Session,
    *,
    organization_id: str | None,
    feature_code: str,
) -> dict[str, Any]:
    if not organization_id:
        raise CostEconomicsError(
            "This work must be connected to an organization before it can run.",
            reason_code="organization_required_for_plan_check",
            status_code=409,
        )
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise CostEconomicsError(
            "Organization not found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    feature = _feature_or_error(feature_code)
    current_plan = resolve_plan_economics(organization.plan_type)
    required_plan = resolve_plan_economics(feature.minimum_plan_code)
    available = _PLAN_LEVEL[current_plan.code] >= _PLAN_LEVEL[required_plan.code]
    result = _feature_payload(feature, current_plan.code)
    if not available:
        raise CommercialPlanFeatureDenied(
            feature=feature,
            current_plan_name=current_plan.name,
            required_plan_name=required_plan.name,
        )
    return result


def get_commercial_plan_summary(
    db: Session,
    *,
    organization: Organization,
) -> dict[str, Any]:
    plan = resolve_plan_economics(organization.plan_type)
    try:
        allowance = get_active_location_allowance(db, organization=organization)
    except ActiveLocationAllowanceError as exc:
        raise CostEconomicsError(
            str(exc),
            reason_code=exc.reason_code,
            status_code=409,
        ) from exc
    capabilities = [_feature_payload(feature, plan.code) for feature in FEATURES]
    return {
        "catalog_version": PLAN_CATALOG_VERSION,
        "plan": {
            "code": plan.code,
            "name": plan.name,
            "monthly_price": float(plan.monthly_revenue),
            "included_locations": allowance.included_locations,
            "active_locations": allowance.active_locations,
            "remaining_locations": allowance.remaining_locations,
            "over_limit_by": allowance.over_limit_by,
            "can_activate_location": allowance.can_activate_location,
            "location_allowance_enforced": allowance.capacity_enforced,
            "additional_locations_require_custom_terms": plan.code == "enterprise",
        },
        "capabilities": capabilities,
        "upgrade": _upgrade_payload(plan.code),
    }


def apply_commercial_plan(
    db: Session,
    *,
    organization_id: str,
    plan_code: str,
    system_billing_transition: bool = False,
) -> tuple[Organization, dict[str, object]]:
    """Materialize the reversible active-location allowance without committing.

    The caller owns commit/rollback. General metered entitlements are intentionally
    not changed in this commercial slice, so their usage ledgers are never reset.
    """
    try:
        canonical_plan_code = normalize_commercial_plan_code(plan_code)
    except ValueError as exc:
        raise CommercialPlanMaterializationError(
            "This billing plan is not supported.",
            reason_code="commercial_plan_unknown",
        ) from exc
    try:
        organization = lock_organization_for_location_allowance(
            db,
            organization_id=organization_id,
        )
    except ActiveLocationAllowanceError as exc:
        raise CommercialPlanMaterializationError(
            str(exc),
            reason_code=exc.reason_code,
        ) from exc
    organization_status = organization.status.strip().lower()
    system_allowed_statuses = {"active", "suspended", "archived", "closure_pending"}
    if organization_status != "active" and not (
        system_billing_transition and organization_status in system_allowed_statuses
    ):
        raise CommercialPlanMaterializationError(
            "The plan cannot be changed while this organization is inactive.",
            reason_code="commercial_plan_organization_inactive",
        )

    legacy_tier_code = legacy_tier_code_for_plan(canonical_plan_code)
    profile = (
        db.query(TierProfile)
        .filter(
            TierProfile.tier_code == legacy_tier_code,
            TierProfile.version == COMMERCIAL_LEGACY_TIER_VERSION,
        )
        .one_or_none()
    )
    if profile is None or not profile.is_active:
        raise CommercialPlanMaterializationError(
            "The requested plan profile is not available.",
            reason_code="commercial_plan_profile_unavailable",
        )
    try:
        validate_commercial_profile_pointer(profile, plan_code=canonical_plan_code)
    except TierProfileValidationError as exc:
        raise CommercialPlanMaterializationError(
            "The requested legacy-compatible plan profile failed its integrity check.",
            reason_code="commercial_plan_profile_mismatch",
        ) from exc
    active_location_template = _active_location_template(canonical_plan_code)

    now = datetime.now(UTC)
    entitlement = (
        db.query(Entitlement)
        .filter(
            Entitlement.organization_id == organization.id,
            Entitlement.code == LIMIT_ACTIVE_LOCATIONS,
        )
        .with_for_update()
        .one_or_none()
    )
    value_type = EntitlementValueType.INTEGER
    reset_period = EntitlementResetPeriod.NONE
    limit_value = int(active_location_template["limit_value"])
    config_json = dict(active_location_template.get("config_json") or {})
    deterministic_hash = _active_location_entitlement_hash(
        organization_id=organization.id,
        value_type=value_type,
        limit_value=limit_value,
        reset_period=reset_period,
        is_enforced=True,
        config_json=config_json,
    )
    entitlement_created = entitlement is None
    if entitlement is None:
        entitlement = Entitlement(
            organization_id=organization.id,
            code=LIMIT_ACTIVE_LOCATIONS,
            value_type=value_type,
            limit_value=limit_value,
            reset_period=reset_period,
            is_enforced=True,
            config_json=config_json,
            deterministic_hash=deterministic_hash,
            created_at=now,
            updated_at=now,
        )
        db.add(entitlement)
    else:
        try:
            validate_canonical_bridge_entitlement(entitlement)
        except ActiveLocationAllowanceError as exc:
            raise CommercialPlanMaterializationError(
                str(exc),
                reason_code=exc.reason_code,
            ) from exc
        entitlement.value_type = value_type
        entitlement.limit_value = limit_value
        entitlement.reset_period = reset_period
        entitlement.is_enforced = True
        entitlement.config_json = config_json
        entitlement.deterministic_hash = deterministic_hash
        entitlement.updated_at = now

    previous_plan_code = organization.plan_type
    previous_tier_profile_id = organization.tier_profile_id
    organization.plan_type = canonical_plan_code
    organization.tier_profile_id = profile.id
    organization.tier_version = int(profile.version)
    organization.updated_at = now
    db.flush()
    return organization, {
        "previous_plan_code": previous_plan_code,
        "plan_code": canonical_plan_code,
        "previous_tier_profile_id": previous_tier_profile_id,
        "tier_profile_id": profile.id,
        "tier_version": int(profile.version),
        "active_location_limit": limit_value,
        "entitlement_created": entitlement_created,
    }


def _active_location_template(plan_code: str) -> dict[str, object]:
    matching = [
        row
        for row in commercial_entitlement_template(plan_code)["entitlements"]
        if isinstance(row, dict) and row.get("code") == LIMIT_ACTIVE_LOCATIONS
    ]
    definition = COMMERCIAL_TIERS[plan_code]
    if len(matching) != 1:
        raise CommercialPlanMaterializationError(
            "The requested plan profile has no valid active-location allowance.",
            reason_code="commercial_plan_location_allowance_invalid",
        )
    item = matching[0]
    if (
        str(item.get("value_type") or "").strip().lower() != "integer"
        or item.get("limit_value") != definition.active_location_limit
        or str(item.get("reset_period") or "").strip().lower() != "none"
        or item.get("is_enforced") is not True
    ):
        raise CommercialPlanMaterializationError(
            "The requested plan profile has an invalid active-location allowance.",
            reason_code="commercial_plan_location_allowance_invalid",
        )
    return item


def _active_location_entitlement_hash(
    *,
    organization_id: str,
    value_type: EntitlementValueType,
    limit_value: int,
    reset_period: EntitlementResetPeriod,
    is_enforced: bool,
    config_json: dict[str, object],
) -> str:
    payload = {
        "organization_id": organization_id,
        "code": LIMIT_ACTIVE_LOCATIONS,
        "value_type": value_type.value,
        "limit_value": limit_value,
        "reset_period": reset_period.value,
        "is_enforced": is_enforced,
        "config_json": config_json,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _feature_payload(feature: CommercialFeature, plan_code: str) -> dict[str, Any]:
    required_plan = resolve_plan_economics(feature.minimum_plan_code)
    return {
        "code": feature.code,
        "label": feature.label,
        "summary": feature.summary,
        "available": _PLAN_LEVEL[plan_code] >= _PLAN_LEVEL[required_plan.code],
        "required_plan": required_plan.name,
    }


def _feature_or_error(feature_code: str) -> CommercialFeature:
    for feature in FEATURES:
        if feature.code == feature_code:
            return feature
    raise CostEconomicsError(
        f"No commercial rule is configured for feature '{feature_code}'.",
        reason_code="commercial_feature_rule_missing",
        status_code=409,
    )


def _upgrade_payload(plan_code: str) -> dict[str, Any] | None:
    if plan_code == "solo":
        target = resolve_plan_economics("multi_location")
        return {
            "plan_code": target.code,
            "plan_name": target.name,
            "monthly_price": float(target.monthly_revenue),
            "headline": "Let InsightOS help carry out the work",
            "reasons": [
                "Approve supported WordPress changes without editing the site by hand.",
                "Use deeper monitoring and automation even if you manage only one business.",
                "Prepare bulk profile work and review-reply workflows with approval controls.",
            ],
        }
    if plan_code == "multi_location":
        target = resolve_plan_economics("enterprise")
        return {
            "plan_code": target.code,
            "plan_name": target.name,
            "monthly_price": float(target.monthly_revenue),
            "headline": "Add custom controls for a larger organization",
            "reasons": [
                "Manage more than 10 locations under custom terms.",
                "Connect approved external automation tools.",
                "Use an approved private or local AI provider.",
            ],
        }
    return None
