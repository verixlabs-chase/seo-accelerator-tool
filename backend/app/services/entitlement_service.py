from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entitlement import Entitlement, EntitlementResetPeriod, EntitlementValueType
from app.models.usage_ledger import UsageLedger


_LOCK_SUPPORTED_DIALECTS = {"postgresql", "mysql", "mariadb", "oracle"}


class EntitlementNotFoundError(Exception):
    pass



def get_entitlement(db: Session, organization_id: str, code: str) -> Entitlement | None:
    return (
        db.query(Entitlement)
        .filter(
            Entitlement.organization_id == organization_id,
            Entitlement.code == code,
        )
        .first()
    )



def can_consume(
    db: Session,
    organization_id: str,
    code: str,
    amount: int = 1,
    now: datetime | None = None,
) -> bool:
    if amount <= 0:
        raise ValueError("amount must be greater than 0")

    resolved_now = _as_utc(now or datetime.now(UTC))
    entitlement = get_entitlement(db, organization_id, code)
    if entitlement is None:
        raise EntitlementNotFoundError(f"Entitlement not found for organization_id={organization_id}, code={code}")

    if not entitlement.is_enforced:
        return True

    if entitlement.value_type == EntitlementValueType.UNLIMITED:
        return True

    if entitlement.limit_value is None:
        return False

    period_start, _ = _resolve_period_window(
        reset_period=entitlement.reset_period,
        now=resolved_now,
    )
    ledger = _select_locked_ledger(
        db,
        organization_id=organization_id,
        entitlement_code=code,
        period_start=period_start,
    )
    consumed_value = 0 if ledger is None else int(ledger.consumed_value)
    next_value = consumed_value + int(amount)
    return next_value <= int(entitlement.limit_value)



def check_and_consume(
    db: Session,
    organization_id: str,
    code: str,
    amount: int = 1,
    now: datetime | None = None,
) -> bool:
    if amount <= 0:
        raise ValueError("amount must be greater than 0")

    resolved_now = _as_utc(now or datetime.now(UTC))
    entitlement = get_entitlement(db, organization_id, code)
    if entitlement is None:
        raise EntitlementNotFoundError(f"Entitlement not found for organization_id={organization_id}, code={code}")

    if not entitlement.is_enforced:
        return True

    if entitlement.value_type == EntitlementValueType.UNLIMITED:
        return True

    if entitlement.limit_value is None:
        return False

    period_start, period_end = _resolve_period_window(
        reset_period=entitlement.reset_period,
        now=resolved_now,
    )
    ledger = _get_or_create_locked_ledger(
        db,
        organization_id=organization_id,
        entitlement_code=code,
        period_start=period_start,
        period_end=period_end,
    )

    next_value = int(ledger.consumed_value) + int(amount)
    if next_value > int(entitlement.limit_value):
        return False

    ledger.consumed_value = next_value
    ledger.deterministic_hash = _usage_ledger_hash(
        organization_id=organization_id,
        entitlement_code=code,
        period_start=ledger.period_start,
        period_end=ledger.period_end,
        consumed_value=ledger.consumed_value,
    )
    ledger.updated_at = resolved_now
    db.flush()
    return True



def _get_or_create_locked_ledger(
    db: Session,
    *,
    organization_id: str,
    entitlement_code: str,
    period_start: datetime,
    period_end: datetime,
) -> UsageLedger:
    row = _select_locked_ledger(
        db,
        organization_id=organization_id,
        entitlement_code=entitlement_code,
        period_start=period_start,
    )
    if row is not None:
        return row

    try:
        with db.begin_nested():
            row = UsageLedger(
                organization_id=organization_id,
                entitlement_code=entitlement_code,
                period_start=period_start,
                period_end=period_end,
                consumed_value=0,
                deterministic_hash=_usage_ledger_hash(
                    organization_id=organization_id,
                    entitlement_code=entitlement_code,
                    period_start=period_start,
                    period_end=period_end,
                    consumed_value=0,
                ),
            )
            db.add(row)
            db.flush()
            return row
    except IntegrityError:
        pass

    existing = _select_locked_ledger(
        db,
        organization_id=organization_id,
        entitlement_code=entitlement_code,
        period_start=period_start,
    )
    if existing is None:
        raise RuntimeError("UsageLedger insert raced but no row could be reloaded")
    return existing



def _select_locked_ledger(
    db: Session,
    *,
    organization_id: str,
    entitlement_code: str,
    period_start: datetime,
) -> UsageLedger | None:
    query = db.query(UsageLedger).filter(
        UsageLedger.organization_id == organization_id,
        UsageLedger.entitlement_code == entitlement_code,
        UsageLedger.period_start == period_start,
    )
    if _supports_row_locking(db):
        query = query.with_for_update()
    return query.first()



def _resolve_period_window(*, reset_period: EntitlementResetPeriod, now: datetime) -> tuple[datetime, datetime]:
    if reset_period == EntitlementResetPeriod.NONE:
        start = now.replace(year=1970, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=365 * 200)
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
    raise ValueError(f"Unsupported reset period: {reset_period}")



def _supports_row_locking(db: Session) -> bool:
    dialect = db.bind.dialect.name.lower() if db.bind is not None else ""
    return dialect in _LOCK_SUPPORTED_DIALECTS



def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)



def _usage_ledger_hash(
    *,
    organization_id: str,
    entitlement_code: str,
    period_start: datetime,
    period_end: datetime,
    consumed_value: int,
) -> str:
    payload = {
        "organization_id": organization_id,
        "entitlement_code": entitlement_code,
        "period_start": _as_utc(period_start).isoformat(),
        "period_end": _as_utc(period_end).isoformat(),
        "consumed_value": int(consumed_value),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()
