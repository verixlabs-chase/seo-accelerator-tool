from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.models.sub_account import SubAccount
from app.schemas.provider_metrics import ProviderExecutionMetricOut
from app.services.provider_metrics_service import ProviderMetricQuery, ProviderMetricsService


router = APIRouter(tags=["provider-metrics"])


@router.get("/provider-metrics")
def list_provider_metrics(
    request: Request,
    provider_name: str | None = Query(default=None),
    capability: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    sub_account_id: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    tenant_id = user["tenant_id"]
    normalized_date_from = _as_utc(date_from)
    normalized_date_to = _as_utc(date_to)
    if normalized_date_from and normalized_date_to and normalized_date_from > normalized_date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "date_from must be less than or equal to date_to.",
                "reason_code": "invalid_date_range",
            },
        )

    if sub_account_id is not None:
        _validate_sub_account_scope(db=db, tenant_id=tenant_id, sub_account_id=sub_account_id)

    service = ProviderMetricsService(db)
    rows, total = service.list_execution_metrics(
        ProviderMetricQuery(
            tenant_id=tenant_id,
            provider_name=provider_name,
            capability=capability,
            outcome=outcome,
            sub_account_id=sub_account_id,
            date_from=normalized_date_from,
            date_to=normalized_date_to,
            limit=limit,
            offset=offset,
        )
    )
    items = [ProviderExecutionMetricOut.model_validate(row).model_dump(mode="json") for row in rows]
    return envelope(
        request,
        {
            "items": items,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "returned": len(items),
                "total": total,
                "has_more": (offset + len(items)) < total,
            },
            "filters": {
                "provider_name": provider_name,
                "capability": capability,
                "outcome": outcome,
                "sub_account_id": sub_account_id,
                "date_from": normalized_date_from.isoformat() if normalized_date_from else None,
                "date_to": normalized_date_to.isoformat() if normalized_date_to else None,
            },
        },
    )


def _validate_sub_account_scope(*, db: Session, tenant_id: str, sub_account_id: str) -> None:
    sub_account = db.query(SubAccount).filter(SubAccount.id == sub_account_id).first()
    if sub_account is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "SubAccount not found.",
                "reason_code": "invalid_sub_account_id",
                "details": {"sub_account_id": sub_account_id},
            },
        )
    if sub_account.organization_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "SubAccount does not belong to the current organization.",
                "reason_code": "sub_account_scope_mismatch",
                "details": {"sub_account_id": sub_account_id},
            },
        )


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
