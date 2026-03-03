from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json

from sqlalchemy.orm import Session

from app.domain import entitlement_codes
from app.models.entitlement import Entitlement, EntitlementResetPeriod, EntitlementValueType
from app.models.organization import Organization
from app.models.tier_profile import TierProfile
from app.services.tier_profile_service import compute_tier_profile_hash


_VALID_ENTITLEMENT_CODES = set(entitlement_codes.ALL_ENTITLEMENT_CODES)
_REQUIRED_TEMPLATE_KEYS = {"entitlements"}
_REQUIRED_ENTITLEMENT_KEYS = {"code", "value_type", "limit_value", "reset_period", "is_enforced"}
_ALLOWED_ENTITLEMENT_KEYS = _REQUIRED_ENTITLEMENT_KEYS | {"config_json"}


class TierChangeValidationError(Exception):
    pass


class TierChangeNotAllowedError(Exception):
    pass



def change_tier(db: Session, organization_id: str, new_tier_profile_id: str) -> dict[str, object]:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise ValueError(f"Organization not found: {organization_id}")
    if organization.status.strip().lower() != "active":
        raise TierChangeNotAllowedError(f"Organization is not active: {organization_id}")

    previous_tier_profile_id = organization.tier_profile_id
    if previous_tier_profile_id == new_tier_profile_id:
        return {
            "entitlements_added": 0,
            "entitlements_disabled": 0,
            "previous_tier_profile_id": previous_tier_profile_id,
            "new_tier_profile_id": new_tier_profile_id,
        }

    tier_profile = db.get(TierProfile, new_tier_profile_id)
    if tier_profile is None:
        raise ValueError(f"TierProfile not found: {new_tier_profile_id}")
    if not tier_profile.is_active:
        raise TierChangeValidationError(f"TierProfile is inactive: {new_tier_profile_id}")

    normalized_template_rows = _validated_entitlement_template_rows(tier_profile.entitlement_template_json)
    _validate_tier_profile(tier_profile, normalized_template_rows=normalized_template_rows)

    now = datetime.now(UTC)

    try:
        existing_rows = (
            db.query(Entitlement)
            .filter(Entitlement.organization_id == organization_id)
            .all()
        )
        existing_by_code = {row.code: row for row in existing_rows}
        template_codes = {str(item["code"]) for item in normalized_template_rows}

        entitlements_added = 0
        for item in normalized_template_rows:
            code = str(item["code"])
            value_type = _coerce_value_type(item["value_type"])
            reset_period = _coerce_reset_period(item["reset_period"])
            limit_value = _normalize_limit_value(value_type=value_type, raw_value=item["limit_value"])
            is_enforced = bool(item["is_enforced"])
            config_json = _normalize_config_json(item.get("config_json", {}))

            row = existing_by_code.get(code)
            if row is None:
                row = Entitlement(
                    organization_id=organization_id,
                    code=code,
                    value_type=value_type,
                    limit_value=limit_value,
                    reset_period=reset_period,
                    is_enforced=is_enforced,
                    config_json=config_json,
                    deterministic_hash=_entitlement_hash(
                        organization_id=organization_id,
                        code=code,
                        value_type=value_type,
                        limit_value=limit_value,
                        reset_period=reset_period,
                        is_enforced=is_enforced,
                        config_json=config_json,
                    ),
                )
                db.add(row)
                existing_by_code[code] = row
                entitlements_added += 1
                continue

            changed = False
            if row.value_type != value_type:
                row.value_type = value_type
                changed = True
            if row.limit_value != limit_value:
                row.limit_value = limit_value
                changed = True
            if row.reset_period != reset_period:
                row.reset_period = reset_period
                changed = True
            if row.is_enforced != is_enforced:
                row.is_enforced = is_enforced
                changed = True
            if _normalize_config_json(row.config_json) != config_json:
                row.config_json = config_json
                changed = True

            if changed:
                row.deterministic_hash = _entitlement_hash(
                    organization_id=organization_id,
                    code=code,
                    value_type=value_type,
                    limit_value=limit_value,
                    reset_period=reset_period,
                    is_enforced=is_enforced,
                    config_json=config_json,
                )
                row.updated_at = now

        entitlements_disabled = 0
        for code, row in existing_by_code.items():
            if code in template_codes:
                continue
            if not row.is_enforced:
                continue
            row.is_enforced = False
            row.deterministic_hash = _entitlement_hash(
                organization_id=organization_id,
                code=row.code,
                value_type=row.value_type,
                limit_value=row.limit_value,
                reset_period=row.reset_period,
                is_enforced=False,
                config_json=_normalize_config_json(row.config_json),
            )
            row.updated_at = now
            entitlements_disabled += 1

        organization.tier_profile_id = tier_profile.id
        organization.tier_version = int(tier_profile.version)
        organization.updated_at = now

        db.flush()
        db.commit()
        return {
            "entitlements_added": entitlements_added,
            "entitlements_disabled": entitlements_disabled,
            "previous_tier_profile_id": previous_tier_profile_id,
            "new_tier_profile_id": tier_profile.id,
        }
    except Exception:
        db.rollback()
        raise



def _validate_tier_profile(
    tier_profile: TierProfile,
    *,
    normalized_template_rows: list[dict[str, object]],
) -> None:
    canonical_template = {
        "tier_code": tier_profile.tier_code,
        "version": tier_profile.version,
        "entitlements": normalized_template_rows,
    }
    computed_hash = compute_tier_profile_hash(canonical_template)
    if computed_hash != tier_profile.deterministic_hash:
        raise TierChangeValidationError(
            f"TierProfile deterministic hash mismatch for tier_profile_id={tier_profile.id}"
        )



def _validated_entitlement_template_rows(raw_template: object) -> list[dict[str, object]]:
    if not isinstance(raw_template, dict):
        raise TierChangeValidationError("TierProfile entitlement_template_json must be an object")
    if set(raw_template.keys()) != _REQUIRED_TEMPLATE_KEYS:
        raise TierChangeValidationError("TierProfile entitlement_template_json must only contain the 'entitlements' key")

    items = raw_template.get("entitlements")
    if not isinstance(items, list):
        raise TierChangeValidationError("TierProfile entitlement_template_json['entitlements'] must be a list")

    normalized: list[dict[str, object]] = []
    seen_codes: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise TierChangeValidationError("Each entitlement template item must be an object")

        keys = set(item.keys())
        if not _REQUIRED_ENTITLEMENT_KEYS.issubset(keys):
            missing = sorted(_REQUIRED_ENTITLEMENT_KEYS - keys)
            raise TierChangeValidationError(f"Entitlement template item missing required keys: {', '.join(missing)}")
        unknown = sorted(keys - _ALLOWED_ENTITLEMENT_KEYS)
        if unknown:
            raise TierChangeValidationError(f"Entitlement template item contains unknown keys: {', '.join(unknown)}")

        code = str(item["code"]).strip()
        if not code:
            raise TierChangeValidationError("Entitlement template code must be a non-empty string")
        if code in seen_codes:
            raise TierChangeValidationError(f"Duplicate entitlement code in TierProfile template: {code}")
        if code not in _VALID_ENTITLEMENT_CODES:
            raise TierChangeValidationError(f"Unsupported entitlement code in TierProfile: {code}")

        value_type = _coerce_value_type(item["value_type"])
        reset_period = _coerce_reset_period(item["reset_period"])
        limit_value = _normalize_limit_value(value_type=value_type, raw_value=item["limit_value"])

        is_enforced = item["is_enforced"]
        if not isinstance(is_enforced, bool):
            raise TierChangeValidationError("Entitlement template is_enforced must be a boolean")

        config_json = item.get("config_json", {})
        if not isinstance(config_json, dict):
            raise TierChangeValidationError("Entitlement template config_json must be an object when provided")

        normalized.append(
            {
                "code": code,
                "value_type": value_type.value,
                "limit_value": limit_value,
                "reset_period": reset_period.value,
                "is_enforced": is_enforced,
                "config_json": config_json,
            }
        )
        seen_codes.add(code)

    return sorted(normalized, key=lambda entry: str(entry["code"]))



def _coerce_value_type(value: object) -> EntitlementValueType:
    normalized = str(value).strip().lower()
    for candidate in EntitlementValueType:
        if candidate.value == normalized:
            return candidate
    raise TierChangeValidationError(f"Unsupported entitlement value_type: {value}")



def _coerce_reset_period(value: object) -> EntitlementResetPeriod:
    normalized = str(value).strip().lower()
    for candidate in EntitlementResetPeriod:
        if candidate.value == normalized:
            return candidate
    raise TierChangeValidationError(f"Unsupported entitlement reset_period: {value}")



def _normalize_limit_value(*, value_type: EntitlementValueType, raw_value: object) -> int | None:
    if value_type == EntitlementValueType.UNLIMITED:
        if raw_value is not None:
            raise TierChangeValidationError("limit_value must be null when value_type is 'unlimited'")
        return None
    if raw_value is None:
        raise TierChangeValidationError(f"limit_value is required for entitlement value_type={value_type.value}")
    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise TierChangeValidationError("limit_value must be an integer or null") from exc



def _normalize_config_json(value: object) -> dict:
    if isinstance(value, dict):
        return value
    raise TierChangeValidationError("config_json must be an object")



def _entitlement_hash(
    *,
    organization_id: str,
    code: str,
    value_type: EntitlementValueType,
    limit_value: int | None,
    reset_period: EntitlementResetPeriod,
    is_enforced: bool,
    config_json: dict,
) -> str:
    payload = {
        "organization_id": organization_id,
        "code": code,
        "value_type": value_type.value,
        "limit_value": limit_value,
        "reset_period": reset_period.value,
        "is_enforced": is_enforced,
        "config_json": config_json,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(serialized.encode("utf-8")).hexdigest()
