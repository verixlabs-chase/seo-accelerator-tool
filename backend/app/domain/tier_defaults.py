from __future__ import annotations

from app.domain.entitlement_codes import ALL_ENTITLEMENT_CODES


DEFAULT_TIER_PROFILE_ID = "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690001"
DEFAULT_TIER_CODE = "standard"
DEFAULT_TIER_VERSION = 1
DEFAULT_TIER_DISPLAY_NAME = "Standard"


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
            for code in sorted(ALL_ENTITLEMENT_CODES)
        ]
    }
