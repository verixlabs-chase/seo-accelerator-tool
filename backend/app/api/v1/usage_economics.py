from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_org_role, require_platform_owner, require_platform_role
from app.api.response import envelope
from app.db.session import get_db
from app.models.organization import Organization
from app.services.audit_service import write_audit_log
from app.services.cost_economics_service import (
    CostEconomicsError,
    get_customer_credit_summary,
    get_margin_report,
    list_tier_margin_models,
    record_monthly_allocation,
)


tenant_router = APIRouter(tags=["usage-economics"])
control_plane_router = APIRouter(tags=["platform-economics"])


class CostAllocationIn(BaseModel):
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    revenue_override: Decimal | None = Field(default=None, ge=0)
    hosting_cost: Decimal = Field(default=Decimal("0"), ge=0)
    storage_cost: Decimal = Field(default=Decimal("0"), ge=0)
    email_cost: Decimal = Field(default=Decimal("0"), ge=0)
    support_cost: Decimal = Field(default=Decimal("0"), ge=0)
    other_cost: Decimal = Field(default=Decimal("0"), ge=0)
    source: str = Field(default="operator", min_length=1, max_length=80)


@tenant_router.get("/usage/credits")
@tenant_router.get("/usage/allowance", include_in_schema=False)
def get_customer_allowance(
    request: Request,
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = get_customer_credit_summary(db, organization_id=user["organization_id"])
    except CostEconomicsError as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@control_plane_router.get("/platform/margins/tiers")
def get_tier_margin_models(
    request: Request,
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
) -> dict:
    return envelope(request, {"items": list_tier_margin_models()})


@control_plane_router.get("/platform/margins")
def list_organization_margins(
    request: Request,
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    period = _parse_month(month) if month else datetime.now(UTC)
    items = []
    for org in db.query(Organization).order_by(Organization.name.asc()).all():
        try:
            items.append(get_margin_report(db, organization_id=org.id, period=period))
        except CostEconomicsError as exc:
            items.append(
                {
                    "organization": {"id": org.id, "name": org.name},
                    "error": {"reason_code": exc.reason_code, "message": str(exc)},
                }
            )
    return envelope(request, {"items": items, "tier_models": list_tier_margin_models()})


@control_plane_router.get("/platform/orgs/{organization_id}/margin")
def get_organization_margin(
    request: Request,
    organization_id: str,
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = get_margin_report(
            db,
            organization_id=organization_id,
            period=_parse_month(month) if month else datetime.now(UTC),
        )
    except CostEconomicsError as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@control_plane_router.post("/platform/orgs/{organization_id}/cost-allocations")
def create_organization_cost_allocation(
    request: Request,
    organization_id: str,
    body: CostAllocationIn,
    user: dict = Depends(require_platform_owner()),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = record_monthly_allocation(
            db,
            organization_id=organization_id,
            period=_parse_month(body.month),
            created_by_user_id=user["id"],
            revenue_override=body.revenue_override,
            hosting_cost=body.hosting_cost,
            storage_cost=body.storage_cost,
            email_cost=body.email_cost,
            support_cost=body.support_cost,
            other_cost=body.other_cost,
            source=body.source,
        )
        report = get_margin_report(
            db,
            organization_id=organization_id,
            period=row.period_start,
        )
        write_audit_log(
            db,
            tenant_id=organization_id,
            actor_user_id=user["id"],
            event_type="platform.org.cost_allocation.created",
            payload={
                "organization_id": organization_id,
                "allocation_id": row.id,
                "period_start": row.period_start.isoformat(),
                "version": row.version,
                "source": row.source,
            },
        )
        db.commit()
    except CostEconomicsError as exc:
        raise _http_error(exc) from exc
    return envelope(
        request,
        {
            "allocation": {
                "id": row.id,
                "version": row.version,
                "period_start": row.period_start.isoformat(),
                "period_end": row.period_end.isoformat(),
                "created_at": row.created_at.isoformat(),
            },
            "margin": report,
        },
    )


def _parse_month(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m").replace(tzinfo=UTC)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "month must use YYYY-MM format.",
                "reason_code": "invalid_month",
            },
        ) from exc


def _http_error(exc: CostEconomicsError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"message": str(exc), "reason_code": exc.reason_code},
    )
