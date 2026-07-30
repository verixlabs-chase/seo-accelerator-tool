from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, Response, status

from app.core.config import get_settings

ACCESS_TOKEN_COOKIE_NAME = "lsos_access_token"
REFRESH_TOKEN_COOKIE_NAME = "lsos_refresh_token"


def create_token(
    *,
    user_id: str,
    organization_id: str | None,
    org_role: str | None,
    platform_role: str | None,
    token_type: str,
    ttl_seconds: int,
    session_id: str | None = None,
    token_id: str | None = None,
) -> str:
    now = datetime.now(UTC)
    legacy_roles: list[str] = []
    if platform_role:
        legacy_roles.append(platform_role)
    if org_role:
        legacy_roles.append(org_role)
        if org_role in {"org_owner", "org_admin"}:
            legacy_roles.append("tenant_admin")
    payload: dict[str, Any] = {
        "sub": user_id,
        "user_id": user_id,
        "tenant_id": organization_id,
        "organization_id": organization_id,
        "org_role": org_role,
        "platform_role": platform_role,
        "roles": legacy_roles,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    if session_id:
        payload["sid"] = session_id
    if token_id:
        payload["jti"] = token_id
    settings = get_settings()
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return decode_signed_payload(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def decode_signed_payload(token: str) -> dict[str, Any]:
    settings = get_settings()
    expired_error: jwt.ExpiredSignatureError | None = None
    for secret in settings.jwt_verification_secrets():
        try:
            return jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
        except jwt.ExpiredSignatureError as exc:
            expired_error = exc
        except jwt.PyJWTError:
            continue
    if expired_error is not None:
        raise expired_error
    raise jwt.InvalidTokenError("Token signature did not match an active or transition key.")


def _cookie_secure() -> bool:
    settings = get_settings()
    return settings.app_env.lower() == "production" or settings.public_base_url.lower().startswith("https://")


def set_auth_cookies(
    response: Response,
    *,
    access_token: str | None,
    refresh_token: str | None,
) -> None:
    settings = get_settings()
    cookie_kwargs = {
        "httponly": True,
        "secure": _cookie_secure(),
        "samesite": "lax",
        "path": "/",
    }

    if access_token:
        response.set_cookie(
            ACCESS_TOKEN_COOKIE_NAME,
            access_token,
            max_age=settings.jwt_access_ttl_seconds,
            **cookie_kwargs,
        )
    else:
        response.delete_cookie(ACCESS_TOKEN_COOKIE_NAME, **cookie_kwargs)

    if refresh_token:
        response.set_cookie(
            REFRESH_TOKEN_COOKIE_NAME,
            refresh_token,
            max_age=settings.jwt_refresh_ttl_seconds,
            **cookie_kwargs,
        )
    else:
        response.delete_cookie(REFRESH_TOKEN_COOKIE_NAME, **cookie_kwargs)


def clear_auth_cookies(response: Response) -> None:
    cookie_kwargs = {
        "httponly": True,
        "secure": _cookie_secure(),
        "samesite": "lax",
        "path": "/",
    }
    response.delete_cookie(ACCESS_TOKEN_COOKIE_NAME, **cookie_kwargs)
    response.delete_cookie(REFRESH_TOKEN_COOKIE_NAME, **cookie_kwargs)
