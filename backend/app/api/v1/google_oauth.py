from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.services.google_oauth_service import (
    GOOGLE_PROVIDER_NAME,
    GoogleOAuthError,
    build_google_oauth_authorization_url,
    exchange_google_authorization_code,
    validate_google_oauth_state,
)
from app.services.provider_credentials_service import upsert_organization_provider_credentials


tenant_router = APIRouter(tags=["google-oauth"])


@tenant_router.post("/organizations/{organization_id}/providers/google/oauth/start")
def google_oauth_start(
    request: Request,
    organization_id: str,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
) -> dict:
    _assert_organization_scope(user, organization_id)
    try:
        authorization_url, state = build_google_oauth_authorization_url(
            organization_id=organization_id,
            user_id=str(user["id"]),
        )
    except GoogleOAuthError as exc:
        _raise_oauth_http_error(exc)
    return envelope(
        request,
        {
            "organization_id": organization_id,
            "provider_name": GOOGLE_PROVIDER_NAME,
            "authorization_url": authorization_url,
            "state": state,
        },
    )


@tenant_router.get("/organizations/{organization_id}/providers/google/oauth/callback")
def google_oauth_callback(
    request: Request,
    organization_id: str,
    code: str = Query(..., min_length=1),
    state: str = Query(..., min_length=1),
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_organization_scope(user, organization_id)
    try:
        state_payload = validate_google_oauth_state(state)
    except GoogleOAuthError as exc:
        _raise_oauth_http_error(exc)

    if state_payload["organization_id"] != organization_id:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Google OAuth state organization mismatch.",
                "reason_code": "oauth_state_org_mismatch",
            },
        )
    if state_payload["user_id"] != user["id"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Google OAuth state user mismatch.",
                "reason_code": "oauth_state_user_mismatch",
            },
        )

    try:
        tokens = exchange_google_authorization_code(code)
    except GoogleOAuthError as exc:
        _raise_oauth_http_error(exc)

    row = upsert_organization_provider_credentials(
        db,
        organization_id=organization_id,
        provider_name=GOOGLE_PROVIDER_NAME,
        auth_mode="oauth2",
        credentials=tokens,
    )
    return envelope(
        request,
        {
            "organization_id": row.organization_id,
            "provider_name": row.provider_name,
            "auth_mode": row.auth_mode,
            "connected": True,
            "updated_at": row.updated_at.isoformat() if row.updated_at else datetime.now(UTC).isoformat(),
        },
    )


def _assert_organization_scope(user: dict, organization_id: str) -> None:
    if user.get("organization_id") != organization_id:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Organization context does not match request scope.",
                "reason_code": "organization_scope_mismatch",
            },
        )


def _raise_oauth_http_error(exc: GoogleOAuthError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"message": str(exc), "reason_code": exc.reason_code},
    ) from exc
