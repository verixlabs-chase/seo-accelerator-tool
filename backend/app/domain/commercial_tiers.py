from __future__ import annotations

from dataclasses import dataclass

from app.domain.entitlement_codes import LIMIT_ACTIVE_LOCATIONS
from app.domain.tier_defaults import default_entitlement_template


COMMERCIAL_TIER_CATALOG_VERSION = "commercial-tiers-2026-08-v2"
COMMERCIAL_TIER_VERSION = 2
COMMERCIAL_LEGACY_TIER_VERSION = 1

COMMERCIAL_LEGACY_PROFILE_IDS = {
    "standard": "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690001",
    "enterprise": "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690002",
    "internal_anchor": "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690003",
}

# Published catalogs are immutable. New entitlement codes require a new catalog
# version instead of silently changing the hashes of already-saved v2 profiles.
_COMMERCIAL_V2_ENTITLEMENT_CODES = (
    "feature.performance_trend",
    "feature.campaign_report",
    "feature.report_export",
    "limit.subaccounts",
    "limit.queue.tokens_per_minute",
    "limit.traffic_fact.provider_calls_monthly",
    "limit.rank.keyword_snapshots_monthly",
    "limit.crawl.pages_monthly",
    "limit.crawl.concurrent_runs",
    "limit.active_locations",
)

COMMERCIAL_PLAN_ALIASES = {
    "standard": "solo",
    "solo": "solo",
    "pro": "multi_location",
    "growth": "multi_location",
    "multi-location": "multi_location",
    "multi_location": "multi_location",
    "enterprise": "enterprise",
    "internal_anchor": "internal_anchor",
}

COMMERCIAL_PLAN_LEGACY_TIER_CODES = {
    "solo": "standard",
    "multi_location": "standard",
    "enterprise": "enterprise",
    "internal_anchor": "internal_anchor",
}


@dataclass(frozen=True)
class CommercialTierDefinition:
    code: str
    display_name: str
    profile_id: str
    active_location_limit: int


COMMERCIAL_TIERS: dict[str, CommercialTierDefinition] = {
    "solo": CommercialTierDefinition(
        code="solo",
        display_name="Solo",
        profile_id="d4e60a70-9c0c-4b8f-8cf9-4c7f0c690101",
        active_location_limit=1,
    ),
    "multi_location": CommercialTierDefinition(
        code="multi_location",
        display_name="Growth",
        profile_id="d4e60a70-9c0c-4b8f-8cf9-4c7f0c690102",
        active_location_limit=10,
    ),
    "enterprise": CommercialTierDefinition(
        code="enterprise",
        display_name="Enterprise",
        profile_id="d4e60a70-9c0c-4b8f-8cf9-4c7f0c690103",
        active_location_limit=20,
    ),
    "internal_anchor": CommercialTierDefinition(
        code="internal_anchor",
        display_name="Internal Anchor",
        profile_id="d4e60a70-9c0c-4b8f-8cf9-4c7f0c690104",
        active_location_limit=20,
    ),
}


def normalize_commercial_plan_code(plan_code: str) -> str:
    normalized = COMMERCIAL_PLAN_ALIASES.get((plan_code or "").strip().lower())
    if normalized is None:
        raise ValueError(f"Unsupported commercial plan code: {plan_code}")
    return normalized


def legacy_tier_code_for_plan(plan_code: str) -> str:
    return COMMERCIAL_PLAN_LEGACY_TIER_CODES[normalize_commercial_plan_code(plan_code)]


def legacy_entitlement_template() -> dict[str, list[dict[str, object]]]:
    """Return the immutable v1 template understood by the previous runtime."""
    return default_entitlement_template()


def commercial_entitlement_template(plan_code: str) -> dict[str, list[dict[str, object]]]:
    definition = COMMERCIAL_TIERS[normalize_commercial_plan_code(plan_code)]
    rows: list[dict[str, object]] = []
    for code in sorted(_COMMERCIAL_V2_ENTITLEMENT_CODES):
        if code == LIMIT_ACTIVE_LOCATIONS:
            rows.append(
                {
                    "code": code,
                    "value_type": "integer",
                    "limit_value": definition.active_location_limit,
                    "reset_period": "none",
                    "is_enforced": True,
                    "config_json": {
                        "catalog_version": COMMERCIAL_TIER_CATALOG_VERSION,
                        "unit": "business_location",
                    },
                }
            )
            continue
        rows.append(
            {
                "code": code,
                "value_type": "unlimited",
                "limit_value": None,
                "reset_period": "none",
                "is_enforced": True,
                "config_json": {},
            }
        )
    return {"entitlements": rows}
