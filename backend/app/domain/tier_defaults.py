from __future__ import annotations

DEFAULT_TIER_PROFILE_ID = "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690001"
DEFAULT_TIER_CODE = "standard"
DEFAULT_TIER_VERSION = 1
DEFAULT_TIER_DISPLAY_NAME = "Standard"

# Standard v1 is historical migration state. Keep this tuple immutable even as
# new entitlement codes are added to the current commercial catalog.
_STANDARD_V1_ENTITLEMENT_CODES = (
    "feature.performance_trend",
    "feature.campaign_report",
    "feature.report_export",
    "limit.subaccounts",
    "limit.queue.tokens_per_minute",
    "limit.traffic_fact.provider_calls_monthly",
    "limit.rank.keyword_snapshots_monthly",
    "limit.crawl.pages_monthly",
    "limit.crawl.concurrent_runs",
)


def default_entitlement_template() -> dict[str, list[dict[str, object]]]:
    """Return a fresh entitlement template for the built-in standard tier."""
    return {
        "entitlements": [
            {
                "code": code,
                "value_type": "unlimited",
                "limit_value": None,
                "reset_period": "none",
                "is_enforced": True,
                "config_json": {},
            }
            for code in sorted(_STANDARD_V1_ENTITLEMENT_CODES)
        ]
    }
