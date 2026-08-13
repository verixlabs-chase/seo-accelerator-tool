from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.api.deps import get_current_user
from app.api.response import envelope
from app.db.session import get_db
from app.services.google_oauth_service import (
    GOOGLE_PROVIDER_NAME,
    GOOGLE_OAUTH_SCOPE_TARGET_GSC,
    GoogleOAuthError,
    build_customer_oauth_return_url,
    build_google_oauth_authorization_url,
    exchange_google_authorization_code,
    upsert_organization_google_oauth_client,
    validate_google_oauth_state,
)
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    upsert_organization_provider_credentials,
)


tenant_router = APIRouter(tags=["google-oauth"], dependencies=[Depends(get_current_user)])
public_router = APIRouter(tags=["google-oauth"])


class GoogleOAuthClientConfigIn(BaseModel):
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)


@tenant_router.post("/organizations/{organization_id}/providers/google/oauth/start")
def google_oauth_start(
    request: Request,
    organization_id: str,
    scope_target: Literal["gsc", "gbp", "analytics"] = Query(
        default=GOOGLE_OAUTH_SCOPE_TARGET_GSC
    ),
    return_path: str | None = Query(default=None, max_length=500),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    def _assert_org_admin(user: dict) -> None:
        if user.get("organization_id") is None:
            raise HTTPException(status_code=403, detail="Organization context required")
        if user.get("org_role") not in {"org_owner", "org_admin"}:
            raise HTTPException(status_code=403, detail="Insufficient org role")

    _assert_org_admin(user)
    _assert_organization_scope(user, organization_id)
    try:
        authorization_url, state = build_google_oauth_authorization_url(
            organization_id=organization_id,
            user_id=user["id"],
            scope_target=scope_target,
            return_path=return_path,
            db=db,
        )
    except GoogleOAuthError as exc:
        _raise_oauth_http_error(exc)
    return envelope(
        request,
        {
            "organization_id": organization_id,
            "provider_name": GOOGLE_PROVIDER_NAME,
            "scope_target": scope_target,
            "authorization_url": authorization_url,
            "state": state,
        },
    )


@public_router.get(
    "/providers/google/oauth/callback",
    response_model=None,
)
def google_oauth_callback_static(
    request: Request,
    code: str = Query(..., min_length=1),
    state: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    return _complete_google_oauth_callback(
        request=request,
        code=code,
        state=state,
        db=db,
    )


@public_router.get(
    "/organizations/{organization_id}/providers/google/oauth/callback",
    response_model=None,
)
def google_oauth_callback(
    request: Request,
    organization_id: str,
    code: str = Query(..., min_length=1),
    state: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    return _complete_google_oauth_callback(
        request=request,
        code=code,
        state=state,
        db=db,
        expected_organization_id=organization_id,
    )


def _complete_google_oauth_callback(
    *,
    request: Request,
    code: str,
    state: str,
    db: Session,
    expected_organization_id: str | None = None,
):
    try:
        state_payload = validate_google_oauth_state(state)
    except GoogleOAuthError as exc:
        _raise_oauth_http_error(exc)

    organization_id = str(state_payload["organization_id"])
    if (
        expected_organization_id is not None
        and organization_id != expected_organization_id
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Google OAuth state organization mismatch.",
                "reason_code": "oauth_state_org_mismatch",
            },
        )

    try:
        tokens = exchange_google_authorization_code(
            code=code,
            organization_id=organization_id,
            db=db,
        )
    except GoogleOAuthError as exc:
        _raise_oauth_http_error(exc)

    try:
        row = upsert_organization_provider_credentials(
            db,
            organization_id=organization_id,
            provider_name=GOOGLE_PROVIDER_NAME,
            auth_mode="oauth2",
            credentials=tokens,
        )
    except ProviderCredentialConfigurationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    return_path = state_payload.get("return_path")
    if isinstance(return_path, str) and return_path:
        return RedirectResponse(
            build_customer_oauth_return_url(return_path, status="connected"),
            status_code=303,
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


@tenant_router.put("/organizations/{organization_id}/providers/google/oauth/client")
def upsert_google_oauth_client(
    request: Request,
    organization_id: str,
    body: GoogleOAuthClientConfigIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    def _assert_org_admin(user: dict) -> None:
        if user.get("organization_id") is None:
            raise HTTPException(status_code=403, detail="Organization context required")
        if user.get("org_role") not in {"org_owner", "org_admin"}:
            raise HTTPException(status_code=403, detail="Insufficient org role")

    _assert_org_admin(user)
    _assert_organization_scope(user, organization_id)
    try:
        row = upsert_organization_google_oauth_client(
            db,
            organization_id=organization_id,
            client_id=body.client_id,
            client_secret=body.client_secret,
        )
    except GoogleOAuthError as exc:
        _raise_oauth_http_error(exc)
    return envelope(
        request,
        {
            "organization_id": row.organization_id,
            "provider_name": row.provider_name,
            "configured": True,
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
