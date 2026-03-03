from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json

from sqlalchemy.orm import Session

from app.domain import entitlement_codes
from app.models.entitlement import Entitlement, EntitlementResetPeriod, EntitlementValueType
from app.models.onboarding_state import (
    ONBOARDING_STATE_ACTIVE,
    ONBOARDING_STATE_ENTITLEMENTS_CREATED,
    ONBOARDING_STATE_INIT,
    ONBOARDING_STATE_LEDGER_INITIALIZED,
    ONBOARDING_STATE_PORTFOLIO_CREATED,
    ONBOARDING_STATE_PROVIDER_BASELINE_READY,
    OnboardingState,
)
from app.models.organization import Organization
from app.models.portfolio import Portfolio
from app.models.provider_policy import ProviderPolicy
from app.models.tier_profile import TierProfile
from app.models.usage_ledger import UsageLedger
from app.services.tier_profile_service import compute_tier_profile_hash

_DEFAULT_PORTFOLIO_CODE = "default"
_DEFAULT_PORTFOLIO_NAME = "Default Portfolio"
_DEFAULT_PROVIDER_POLICY_BASELINE: dict[str, str] = {
    "google": "byo_optional",
    "dataforseo": "byo_optional",
    "rank_http": "byo_optional",
    "email": "platform",
}
_VALID_ENTITLEMENT_CODES = set(entitlement_codes.ALL_ENTITLEMENT_CODES)
_REQUIRED_TEMPLATE_KEYS = {"entitlements"}
_REQUIRED_ENTITLEMENT_KEYS = {"code", "value_type", "limit_value", "reset_period", "is_enforced"}
_ALLOWED_ENTITLEMENT_KEYS = _REQUIRED_ENTITLEMENT_KEYS | {"config_json"}


@dataclass(frozen=True)
class ProvisioningResult:
    organization_id: str
    tier_profile_id: str
    onboarding_state_id: str
    final_state: str
    entitlements_created: int
    ledgers_created: int
    portfolio_created: bool
    provider_policies_created: int


class TierProfileValidationError(Exception):
    pass


def provision_organization(
    db: Session,
    *,
    organization_id: str,
    tier_profile_id: str,
) -> ProvisioningResult:
    now = datetime.now(UTC)
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise ValueError(f"Organization not found: {organization_id}")

    tier_profile = db.get(TierProfile, tier_profile_id)
    if tier_profile is None:
        raise ValueError(f"TierProfile not found: {tier_profile_id}")
    if not bool(tier_profile.is_active):
        raise ValueError(f"TierProfile is inactive: {tier_profile_id}")

    normalized_template_rows = _validated_entitlement_template_rows(tier_profile.entitlement_template_json)
    _validate_tier_profile(tier_profile, normalized_template_rows=normalized_template_rows)

    try:
        onboarding_state = _ensure_onboarding_state(db, organization_id=organization_id, now=now)

        entitlements_created = _ensure_entitlements(
            db,
            organization_id=organization_id,
            normalized_template_rows=normalized_template_rows,
        )
        _set_onboarding_state(
            onboarding_state,
            state=ONBOARDING_STATE_ENTITLEMENTS_CREATED,
            now=now,
        )

        ledgers_created = _ensure_usage_ledgers(
            db,
            organization_id=organization_id,
            now=now,
        )
        _set_onboarding_state(
            onboarding_state,
            state=ONBOARDING_STATE_LEDGER_INITIALIZED,
            now=now,
        )

        portfolio_created = _ensure_default_portfolio(
            db,
            organization_id=organization_id,
            tier_code=tier_profile.tier_code,
        )
        _set_onboarding_state(
            onboarding_state,
            state=ONBOARDING_STATE_PORTFOLIO_CREATED,
            now=now,
        )

        provider_policies_created = _ensure_provider_policy_baseline(
            db,
            organization_id=organization_id,
        )
        _set_onboarding_state(
            onboarding_state,
            state=ONBOARDING_STATE_PROVIDER_BASELINE_READY,
            now=now,
        )

        _set_onboarding_state(
            onboarding_state,
            state=ONBOARDING_STATE_ACTIVE,
            now=now,
        )

        db.commit()
        return ProvisioningResult(
            organization_id=organization_id,
            tier_profile_id=tier_profile_id,
            onboarding_state_id=onboarding_state.id,
            final_state=onboarding_state.state,
            entitlements_created=entitlements_created,
            ledgers_created=ledgers_created,
            portfolio_created=portfolio_created,
            provider_policies_created=provider_policies_created,
        )
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
        raise TierProfileValidationError(
            f"TierProfile deterministic hash mismatch for tier_profile_id={tier_profile.id}"
        )


def _ensure_onboarding_state(db: Session, *, organization_id: str, now: datetime) -> OnboardingState:
    row = (
        db.query(OnboardingState)
        .filter(OnboardingState.organization_id == organization_id)
        .first()
    )
    if row is None:
        row = OnboardingState(
            organization_id=organization_id,
            state=ONBOARDING_STATE_INIT,
            last_transition_at=now,
            deterministic_hash=_state_hash(organization_id=organization_id, state=ONBOARDING_STATE_INIT),
        )
        db.add(row)
        db.flush()
    return row


def _ensure_entitlements(
    db: Session,
    *,
    organization_id: str,
    normalized_template_rows: list[dict[str, object]],
) -> int:
    existing_codes = {
        row.code
        for row in db.query(Entitlement).filter(Entitlement.organization_id == organization_id).all()
    }

    created = 0
    for item in normalized_template_rows:
        code = str(item["code"])
        if code in existing_codes:
            continue

        value_type = _coerce_value_type(item["value_type"])
        reset_period = _coerce_reset_period(item["reset_period"])
        limit_value = _normalize_limit_value(value_type=value_type, raw_value=item["limit_value"])
        is_enforced = item["is_enforced"] is True
        config_json = _normalize_config_json(item.get("config_json", {}))

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
        existing_codes.add(code)
        created += 1

    if created > 0:
        db.flush()
    return created


def _ensure_usage_ledgers(db: Session, *, organization_id: str, now: datetime) -> int:
    entitlements = (
        db.query(Entitlement)
        .filter(Entitlement.organization_id == organization_id)
        .all()
    )
    created = 0

    for entitlement in entitlements:
        if entitlement.reset_period == EntitlementResetPeriod.NONE:
            continue
        period_start, period_end = _resolve_period_window(reset_period=entitlement.reset_period, now=now)
        existing = (
            db.query(UsageLedger)
            .filter(
                UsageLedger.organization_id == organization_id,
                UsageLedger.entitlement_code == entitlement.code,
                UsageLedger.period_start == period_start,
            )
            .first()
        )
        if existing is not None:
            continue

        row = UsageLedger(
            organization_id=organization_id,
            entitlement_code=entitlement.code,
            period_start=period_start,
            period_end=period_end,
            consumed_value=0,
            deterministic_hash=_usage_ledger_hash(
                organization_id=organization_id,
                entitlement_code=entitlement.code,
                period_start=period_start,
                period_end=period_end,
                consumed_value=0,
            ),
        )
        db.add(row)
        created += 1

    if created > 0:
        db.flush()
    return created


def _ensure_default_portfolio(db: Session, *, organization_id: str, tier_code: str) -> bool:
    existing = (
        db.query(Portfolio)
        .filter(
            Portfolio.organization_id == organization_id,
            Portfolio.code == _DEFAULT_PORTFOLIO_CODE,
        )
        .first()
    )
    if existing is not None:
        return False

    row = Portfolio(
        organization_id=organization_id,
        name=_DEFAULT_PORTFOLIO_NAME,
        code=_DEFAULT_PORTFOLIO_CODE,
        timezone="UTC",
        default_sla_tier=tier_code.strip().lower(),
    )
    db.add(row)
    db.flush()
    return True


def _ensure_provider_policy_baseline(db: Session, *, organization_id: str) -> int:
    existing = {
        row.provider_name
        for row in db.query(ProviderPolicy).filter(ProviderPolicy.organization_id == organization_id).all()
    }
    created = 0
    for provider_name, credential_mode in _DEFAULT_PROVIDER_POLICY_BASELINE.items():
        if provider_name in existing:
            continue
        row = ProviderPolicy(
            organization_id=organization_id,
            provider_name=provider_name,
            credential_mode=credential_mode,
        )
        db.add(row)
        existing.add(provider_name)
        created += 1
    if created > 0:
        db.flush()
    return created


def _set_onboarding_state(row: OnboardingState, *, state: str, now: datetime) -> None:
    if row.state == state:
        return
    row.state = state
    row.last_transition_at = now
    row.deterministic_hash = _state_hash(organization_id=row.organization_id, state=state)


def _validated_entitlement_template_rows(raw_template: object) -> list[dict[str, object]]:
    if not isinstance(raw_template, dict):
        raise TierProfileValidationError("TierProfile entitlement_template_json must be an object")
    if set(raw_template.keys()) != _REQUIRED_TEMPLATE_KEYS:
        raise TierProfileValidationError("TierProfile entitlement_template_json must only contain the 'entitlements' key")

    items = raw_template.get("entitlements")
    if not isinstance(items, list):
        raise TierProfileValidationError("TierProfile entitlement_template_json['entitlements'] must be a list")

    normalized: list[dict[str, object]] = []
    seen_codes: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise TierProfileValidationError("Each entitlement template item must be an object")
        keys = set(item.keys())
        if not _REQUIRED_ENTITLEMENT_KEYS.issubset(keys):
            missing = sorted(_REQUIRED_ENTITLEMENT_KEYS - keys)
            raise TierProfileValidationError(f"Entitlement template item missing required keys: {', '.join(missing)}")
        unknown = sorted(keys - _ALLOWED_ENTITLEMENT_KEYS)
        if unknown:
            raise TierProfileValidationError(f"Entitlement template item contains unknown keys: {', '.join(unknown)}")

        code = str(item["code"]).strip()
        if not code:
            raise TierProfileValidationError("Entitlement template code must be a non-empty string")
        if code in seen_codes:
            raise TierProfileValidationError(f"Duplicate entitlement code in TierProfile template: {code}")
        if code not in _VALID_ENTITLEMENT_CODES:
            raise TierProfileValidationError(f"Unsupported entitlement code in TierProfile: {code}")

        value_type = _coerce_value_type(item["value_type"])
        reset_period = _coerce_reset_period(item["reset_period"])
        limit_value = _normalize_limit_value(value_type=value_type, raw_value=item["limit_value"])

        is_enforced = item["is_enforced"]
        if not isinstance(is_enforced, bool):
            raise TierProfileValidationError("Entitlement template is_enforced must be a boolean")

        config_json = item.get("config_json", {})
        if not isinstance(config_json, dict):
            raise TierProfileValidationError("Entitlement template config_json must be an object when provided")

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
    raise TierProfileValidationError(f"Unsupported entitlement value_type: {value}")


def _coerce_reset_period(value: object) -> EntitlementResetPeriod:
    normalized = str(value).strip().lower()
    for candidate in EntitlementResetPeriod:
        if candidate.value == normalized:
            return candidate
    raise TierProfileValidationError(f"Unsupported entitlement reset_period: {value}")


def _normalize_limit_value(*, value_type: EntitlementValueType, raw_value: object) -> int | None:
    if value_type == EntitlementValueType.UNLIMITED:
        if raw_value is not None:
            raise TierProfileValidationError("limit_value must be null when value_type is 'unlimited'")
        return None
    if raw_value is None:
        raise TierProfileValidationError(f"limit_value is required for entitlement value_type={value_type.value}")
    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise TierProfileValidationError("limit_value must be an integer or null") from exc


def _normalize_config_json(value: object) -> dict:
    if isinstance(value, dict):
        return value
    raise TierProfileValidationError("config_json must be an object")


def _resolve_period_window(*, reset_period: EntitlementResetPeriod, now: datetime) -> tuple[datetime, datetime]:
    if reset_period == EntitlementResetPeriod.DAILY:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if reset_period == EntitlementResetPeriod.MONTHLY:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    raise ValueError(f"UsageLedger cannot be initialized for reset_period={reset_period.value}")


def _state_hash(*, organization_id: str, state: str) -> str:
    return _stable_hash({
        "organization_id": organization_id,
        "state": state,
    })


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
    return _stable_hash(
        {
            "organization_id": organization_id,
            "code": code,
            "value_type": value_type.value,
            "limit_value": limit_value,
            "reset_period": reset_period.value,
            "is_enforced": is_enforced,
            "config_json": config_json,
        }
    )


def _usage_ledger_hash(
    *,
    organization_id: str,
    entitlement_code: str,
    period_start: datetime,
    period_end: datetime,
    consumed_value: int,
) -> str:
    return _stable_hash(
        {
            "organization_id": organization_id,
            "entitlement_code": entitlement_code,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "consumed_value": consumed_value,
        }
    )


def _stable_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(serialized.encode("utf-8")).hexdigest()
