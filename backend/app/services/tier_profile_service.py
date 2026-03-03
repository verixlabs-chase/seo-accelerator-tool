from __future__ import annotations

from hashlib import sha256
import json


def compute_tier_profile_hash(template_json: dict) -> str:
    tier_code = str(template_json["tier_code"]).strip().lower()
    version = int(template_json["version"])
    raw_entitlements = template_json["entitlements"]
    if not isinstance(raw_entitlements, list):
        raise ValueError("entitlements must be a list")

    normalized_entitlements: list[dict[str, object]] = []
    for item in raw_entitlements:
        if not isinstance(item, dict):
            raise ValueError("each entitlement must be an object")
        normalized_entitlements.append(
            {
                "code": str(item["code"]).strip(),
                "value_type": str(item["value_type"]).strip().lower(),
                "limit_value": item["limit_value"],
                "reset_period": str(item["reset_period"]).strip().lower(),
                "is_enforced": bool(item["is_enforced"]),
                "config_json": item.get("config_json", {}),
            }
        )

    canonical_payload = {
        "tier_code": tier_code,
        "version": version,
        "entitlements": sorted(normalized_entitlements, key=lambda item: item["code"]),
    }
    serialized = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(serialized.encode("utf-8")).hexdigest()
