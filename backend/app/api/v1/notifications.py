from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.services import notification_service


router = APIRouter(prefix="/notifications", tags=["notifications"])
notification_member = require_org_role({"org_user"})


@router.get("")
def get_notifications(
    request: Request,
    response: Response,
    location_id: str | None = Query(default=None, min_length=36, max_length=36),
    include_dismissed: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
    user: dict = Depends(notification_member),
    db: Session = Depends(get_db),
) -> dict:
    _set_private_response_headers(response)
    payload = notification_service.list_notifications(
        db,
        tenant_id=str(user["tenant_id"]),
        organization_id=str(user["organization_id"]),
        user_id=str(user["id"]),
        location_id=location_id,
        include_dismissed=include_dismissed,
        limit=limit,
        offset=offset,
    )
    return envelope(request, payload.model_dump(mode="json"))


@router.get("/unread-count")
def get_notification_unread_count(
    request: Request,
    response: Response,
    location_id: str | None = Query(default=None, min_length=36, max_length=36),
    user: dict = Depends(notification_member),
    db: Session = Depends(get_db),
) -> dict:
    _set_private_response_headers(response)
    payload = notification_service.notification_unread_count_payload(
        db,
        tenant_id=str(user["tenant_id"]),
        organization_id=str(user["organization_id"]),
        user_id=str(user["id"]),
        location_id=location_id,
    )
    return envelope(request, payload.model_dump(mode="json"))


@router.patch("/{notification_id}/read")
def patch_notification_read(
    notification_id: str,
    request: Request,
    response: Response,
    user: dict = Depends(notification_member),
    db: Session = Depends(get_db),
) -> dict:
    _set_private_response_headers(response)
    try:
        payload = notification_service.mark_notification_read(
            db,
            tenant_id=str(user["tenant_id"]),
            organization_id=str(user["organization_id"]),
            user_id=str(user["id"]),
            notification_id=notification_id,
        )
        db.commit()
    except notification_service.NotificationError as exc:
        db.rollback()
        _raise_notification_error(exc)
    return envelope(request, payload.model_dump(mode="json"))


@router.patch("/{notification_id}/dismiss")
def patch_notification_dismiss(
    notification_id: str,
    request: Request,
    response: Response,
    user: dict = Depends(notification_member),
    db: Session = Depends(get_db),
) -> dict:
    _set_private_response_headers(response)
    try:
        payload = notification_service.dismiss_notification(
            db,
            tenant_id=str(user["tenant_id"]),
            organization_id=str(user["organization_id"]),
            user_id=str(user["id"]),
            notification_id=notification_id,
        )
        db.commit()
    except notification_service.NotificationError as exc:
        db.rollback()
        _raise_notification_error(exc)
    return envelope(request, payload.model_dump(mode="json"))


def _set_private_response_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"


def _raise_notification_error(exc: notification_service.NotificationError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"message": str(exc), "reason_code": exc.reason_code},
    ) from exc
