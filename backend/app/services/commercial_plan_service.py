from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.models.organization import Organization
from app.services.cost_economics_service import CostEconomicsError, resolve_plan_economics


PLAN_CATALOG_VERSION = "commercial-plans-2026-08-v1"

FEATURE_WORDPRESS_EXECUTION = "wordpress_execution"
FEATURE_PROFILE_FLEET_ACTIONS = "business_profile_fleet_actions"
FEATURE_AUTOMATIC_REVIEW_REPLIES = "automatic_review_replies"
FEATURE_EXTERNAL_AUTOMATION = "external_automation"
FEATURE_PRIVATE_AI_PROVIDER = "private_ai_provider"

_PLAN_LEVEL = {
    "solo": 1,
    "multi_location": 2,
    "enterprise": 3,
}

_INCLUDED_LOCATIONS = {
    "solo": 1,
    "multi_location": 10,
    "enterprise": 20,
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
    included_locations = _INCLUDED_LOCATIONS[plan.code]
    active_locations = int(
        db.query(func.count(BusinessLocation.id))
        .filter(
            BusinessLocation.organization_id == organization.id,
            BusinessLocation.status == "active",
        )
        .scalar()
        or 0
    )
    capabilities = [_feature_payload(feature, plan.code) for feature in FEATURES]
    return {
        "catalog_version": PLAN_CATALOG_VERSION,
        "plan": {
            "code": plan.code,
            "name": plan.name,
            "monthly_price": float(plan.monthly_revenue),
            "included_locations": included_locations,
            "active_locations": active_locations,
            "remaining_locations": max(0, included_locations - active_locations),
            "additional_locations_require_custom_terms": plan.code == "enterprise",
        },
        "capabilities": capabilities,
        "upgrade": _upgrade_payload(plan.code),
    }


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
