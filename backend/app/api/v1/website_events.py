from __future__ import annotations

from datetime import datetime
import re
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import enforce_organization_scope, require_org_role
from app.api.response import envelope
from app.db.session import get_db, set_session_security_context
from app.services import website_event_service


tenant_router = APIRouter(tags=["website-events"])
public_router = APIRouter(tags=["website-events"])
_BEARER_PATTERN = re.compile(r"^Bearer\s+(.+)$", re.IGNORECASE)


class WebsiteFormEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    event_name: Literal["form_submitted", "inquiry_confirmed"]
    page_url: str = Field(..., min_length=8, max_length=2048)
    form_id: str | None = Field(default=None, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    occurred_at: datetime


def _raise_event_error(exc: website_event_service.WebsiteEventError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"message": str(exc), "reason_code": exc.reason_code},
    ) from exc


@tenant_router.post(
    "/organizations/{organization_id}/data-connections/{connection_id}/website-events/key"
)
def rotate_website_event_key(
    request: Request,
    organization_id: str,
    connection_id: str,
    user: dict = Depends(require_org_role({"org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    enforce_organization_scope(user=user, organization_id=organization_id, allow_platform=False)
    try:
        payload = website_event_service.rotate_ingest_token(
            db,
            organization_id=organization_id,
            connection_id=connection_id,
        )
    except website_event_service.WebsiteEventError as exc:
        _raise_event_error(exc)
    return envelope(request, payload)


@public_router.post("/website-events/forms/{connection_id}")
def receive_website_form_event(
    request: Request,
    connection_id: str,
    body: WebsiteFormEventIn,
    authorization: str = Header(default="", alias="Authorization"),
    db: Session = Depends(get_db),
) -> dict:
    match = _BEARER_PATTERN.match(authorization.strip())
    if match is None or not match.group(1).strip():
        raise HTTPException(
            status_code=401,
            detail={
                "message": "A website event connection key is required.",
                "reason_code": "website_event_key_required",
            },
        )
    set_session_security_context(
        db,
        tenant_id=None,
        organization_id=None,
        user_id="website-event-ingest",
        platform_access=True,
    )
    try:
        payload = website_event_service.ingest_form_event(
            db,
            connection_id=connection_id,
            bearer_token=match.group(1),
            event_id=body.event_id,
            event_name=body.event_name,
            page_url=body.page_url,
            form_id=body.form_id,
            occurred_at=body.occurred_at,
        )
    except website_event_service.WebsiteEventError as exc:
        _raise_event_error(exc)
    return envelope(request, payload)
