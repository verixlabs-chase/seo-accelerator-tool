from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_org_role, require_platform_role
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.support import (
    SupportRequestCreateIn,
    SupportRequestEscalateIn,
    SupportRequestStatusPatchIn,
)
from app.services import support_service


tenant_router = APIRouter(prefix="/support/requests", tags=["support"])
control_plane_router = APIRouter(prefix="/platform/support/requests", tags=["platform-support"])


def _translate_error(exc: support_service.SupportRequestError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"message": str(exc), "reason_code": exc.reason_code},
    )


@tenant_router.post("")
def create_support_request(
    request: Request,
    body: SupportRequestCreateIn,
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = support_service.create_support_request(
            db,
            tenant_id=user["tenant_id"],
            organization_id=user["organization_id"],
            actor_user_id=user["id"],
            **body.model_dump(),
        )
    except support_service.SupportRequestError as exc:
        raise _translate_error(exc) from exc
    db.commit()
    db.refresh(row)
    return envelope(request, {"request": support_service.serialize_support_request(row)})


@tenant_router.get("")
def list_support_requests(
    request: Request,
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    rows = support_service.list_support_requests(
        db, organization_id=user["organization_id"]
    )
    return envelope(
        request,
        {"items": [support_service.serialize_support_request(row) for row in rows]},
    )


@tenant_router.post("/{request_id}/escalate")
def escalate_support_request(
    request: Request,
    request_id: str,
    body: SupportRequestEscalateIn,
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = support_service.escalate_support_request(
            db,
            organization_id=user["organization_id"],
            request_id=request_id,
            reason=body.reason,
        )
    except support_service.SupportRequestError as exc:
        raise _translate_error(exc) from exc
    db.commit()
    db.refresh(row)
    return envelope(request, {"request": support_service.serialize_support_request(row)})


@control_plane_router.patch("/{request_id}")
def update_support_request(
    request: Request,
    request_id: str,
    body: SupportRequestStatusPatchIn,
    user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = support_service.update_support_request_status(
            db,
            request_id=request_id,
            status=body.status,
            note_code=body.note_code,
            actor_user_id=user["id"],
        )
    except support_service.SupportRequestError as exc:
        raise _translate_error(exc) from exc
    db.commit()
    db.refresh(row)
    return envelope(
        request,
        {"request": support_service.serialize_support_request(row, include_diagnostics=True)},
    )


@control_plane_router.get("")
def list_platform_support_requests(
    request: Request,
    organization_id: str | None = None,
    status: str | None = Query(
        default=None,
        pattern="^(received|investigating|waiting_for_customer|escalated|resolved)$",
    ),
    limit: int = Query(default=100, ge=1, le=200),
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    rows = support_service.list_platform_support_requests(
        db,
        organization_id=organization_id,
        status=status,
        limit=limit,
    )
    return envelope(
        request,
        {
            "items": [
                support_service.serialize_support_request(row, include_diagnostics=True)
                for row in rows
            ]
        },
    )
