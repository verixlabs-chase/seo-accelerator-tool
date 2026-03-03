from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.entitlement import Entitlement, EntitlementValueType
from app.models.usage_ledger import UsageLedger
from app.services.entitlement_service import _as_utc, _resolve_period_window



def get_entitlement_status(db: Session, organization_id: str) -> list[dict]:
    entitlements = (
        db.query(Entitlement)
        .filter(Entitlement.organization_id == organization_id)
        .order_by(Entitlement.code.asc())
        .all()
    )

    now = datetime.now(UTC)
    rows: list[dict] = []
    for entitlement in entitlements:
        rows.append(_build_entitlement_status_row(db, entitlement=entitlement, now=now))
    return rows



def _build_entitlement_status_row(db: Session, *, entitlement: Entitlement, now: datetime) -> dict:
    base_row = {
        "code": entitlement.code,
        "value_type": entitlement.value_type.value,
        "limit_value": entitlement.limit_value,
        "reset_period": entitlement.reset_period.value,
        "is_enforced": entitlement.is_enforced,
        "consumed_value": None,
        "remaining_value": None,
        "percent_consumed": None,
        "period_start": None,
        "period_end": None,
    }

    if not entitlement.is_enforced:
        return base_row

    if entitlement.value_type == EntitlementValueType.UNLIMITED:
        return base_row

    if entitlement.limit_value is None:
        return base_row

    period_start, period_end = _resolve_period_window(
        reset_period=entitlement.reset_period,
        now=_as_utc(now),
    )
    ledger = (
        db.query(UsageLedger)
        .filter(
            UsageLedger.organization_id == entitlement.organization_id,
            UsageLedger.entitlement_code == entitlement.code,
            UsageLedger.period_start == period_start,
        )
        .first()
    )
    consumed_value = 0 if ledger is None else int(ledger.consumed_value)
    remaining_value = max(0, int(entitlement.limit_value) - consumed_value)
    percent_consumed = _calculate_percent_consumed(
        consumed_value=consumed_value,
        limit_value=int(entitlement.limit_value),
    )

    base_row["consumed_value"] = consumed_value
    base_row["remaining_value"] = remaining_value
    base_row["percent_consumed"] = percent_consumed
    base_row["period_start"] = period_start
    base_row["period_end"] = period_end
    return base_row



def _calculate_percent_consumed(*, consumed_value: int, limit_value: int) -> float:
    if limit_value <= 0:
        return 100.0
    percent = (float(consumed_value) / float(limit_value)) * 100.0
    return round(min(max(percent, 0.0), 100.0), 2)
