from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner, require_platform_role
from app.api.response import envelope
from app.db.session import get_db
from app.services.customer_status_service import (
    CustomerStatusError,
    create_customer_status_update,
    customer_status_history,
    customer_status_summary,
    serialize_customer_status_update,
)


tenant_router = APIRouter(prefix="/status", tags=["customer-status"])
control_plane_router = APIRouter(prefix="/system/customer-status", tags=["customer-status"])


class CustomerStatusUpdateIn(BaseModel):
    incident_key: str = Field(min_length=3, max_length=64)
    state: Literal["investigating", "identified", "monitoring", "resolved", "maintenance"]
    impact: Literal["none", "minor", "major", "critical"]
    title: str = Field(min_length=8, max_length=100)
    message: str = Field(min_length=20, max_length=500)
    affected_surfaces: list[
        Literal[
            "dashboard",
            "website_analysis",
            "rankings",
            "local_visibility",
            "reviews",
            "reports",
            "automations",
            "billing",
            "connections",
            "sign_in",
        ]
    ] = Field(min_length=1, max_length=10)
    visible_to_customers: bool = True
    starts_at: datetime
    ends_at: datetime | None = None


@tenant_router.get("/summary")
def get_customer_status_summary(
    request: Request,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> dict:
    return envelope(request, customer_status_summary(db))


@control_plane_router.get("")
def get_customer_status_history(
    request: Request,
    limit: int = Query(default=100, ge=1, le=250),
    db: Session = Depends(get_db),
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
) -> dict:
    return envelope(request, customer_status_history(db, limit=limit))


@control_plane_router.post("")
def record_customer_status_update(
    request: Request,
    body: CustomerStatusUpdateIn,
    db: Session = Depends(get_db),
    user: dict = Depends(require_platform_owner()),
) -> dict:
    try:
        update, created = create_customer_status_update(
            db,
            incident_key=body.incident_key,
            state=body.state,
            impact=body.impact,
            title=body.title,
            message=body.message,
            affected_surfaces=list(body.affected_surfaces),
            visible_to_customers=body.visible_to_customers,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            created_by_user_id=user["id"],
        )
        db.commit()
        db.refresh(update)
    except CustomerStatusError as exc:
        db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    return envelope(
        request,
        {
            "created": created,
            "update": serialize_customer_status_update(update, internal=True),
            "status": customer_status_history(db),
        },
    )
