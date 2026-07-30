from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.response import envelope
from app.core.security import (
    ACCESS_TOKEN_COOKIE_NAME,
    REFRESH_TOKEN_COOKIE_NAME,
    clear_auth_cookies,
    set_auth_cookies,
)
from app.db.session import get_db
from app.schemas.auth import LoginRequest, OrgSelectionRequest, RefreshRequest
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _refresh_token_from_request(request: Request, body_token: str | None) -> str:
    token = body_token or request.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh session")
    return token


def _access_token_from_request(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)


@router.post("/login")
def login(request: Request, response: Response, body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    payload = auth_service.login(db, body.email, body.password, body.organization_id)
    request.state.tenant_id = payload["user"]["organization_id"]
    set_auth_cookies(
        response,
        access_token=payload.get("access_token"),
        refresh_token=payload.get("refresh_token"),
    )
    return envelope(request, payload)


@router.post("/refresh")
def refresh(request: Request, response: Response, body: RefreshRequest | None = None, db: Session = Depends(get_db)) -> dict:
    payload = auth_service.refresh(db, _refresh_token_from_request(request, body.refresh_token if body else None))
    request.state.tenant_id = payload["user"]["organization_id"]
    set_auth_cookies(
        response,
        access_token=payload.get("access_token"),
        refresh_token=payload.get("refresh_token"),
    )
    return envelope(request, payload)


@router.post("/select-org")
def select_org(request: Request, response: Response, body: OrgSelectionRequest, db: Session = Depends(get_db)) -> dict:
    payload = auth_service.select_organization(db, _refresh_token_from_request(request, body.refresh_token), body.organization_id)
    request.state.tenant_id = payload["user"]["organization_id"]
    set_auth_cookies(
        response,
        access_token=payload.get("access_token"),
        refresh_token=payload.get("refresh_token"),
    )
    return envelope(request, payload)


@router.get("/me")
def me(request: Request, user: dict = Depends(get_current_user)) -> dict:
    return envelope(request, user)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    token = _access_token_from_request(request)
    revoked = auth_service.revoke_session_from_token(db, token) if token else False
    clear_auth_cookies(response)
    request.state.tenant_id = None
    return envelope(request, {"logged_out": True, "session_revoked": revoked})


@router.get("/sessions")
def sessions(
    request: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(
        request,
        {
            "sessions": auth_service.list_active_sessions(
                db,
                user_id=str(user["user_id"]),
            )
        },
    )


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    revoked = auth_service.revoke_user_session(
        db,
        user_id=str(user["user_id"]),
        session_id=session_id,
    )
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active session not found")
    return envelope(request, {"session_id": session_id, "revoked": True})
