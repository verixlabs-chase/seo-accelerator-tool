from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import jwt
import requests  # type: ignore[import-untyped]

from app.core.settings import get_settings


GOOGLE_PROVIDER_NAME = "google"


class GoogleOAuthError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def build_google_oauth_authorization_url(*, organization_id: str, user_id: str) -> tuple[str, str]:
    settings = get_settings()
    _require_google_oauth_configuration()
    state = create_google_oauth_state(organization_id=organization_id, user_id=user_id)
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": settings.google_oauth_scope,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{settings.google_oauth_auth_endpoint}?{urlencode(params)}", state


def create_google_oauth_state(*, organization_id: str, user_id: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "type": "google_oauth_state",
        "organization_id": organization_id,
        "user_id": user_id,
        "nonce": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + settings.google_oauth_state_ttl_seconds,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def validate_google_oauth_state(state: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise GoogleOAuthError(
            "Google OAuth state expired.",
            reason_code="oauth_state_expired",
            status_code=400,
        ) from exc
    except jwt.PyJWTError as exc:
        raise GoogleOAuthError(
            "Google OAuth state is invalid.",
            reason_code="oauth_state_invalid",
            status_code=400,
        ) from exc

    if payload.get("type") != "google_oauth_state":
        raise GoogleOAuthError(
            "Google OAuth state is invalid.",
            reason_code="oauth_state_invalid",
            status_code=400,
        )
    organization_id = payload.get("organization_id")
    user_id = payload.get("user_id")
    if not isinstance(organization_id, str) or not organization_id:
        raise GoogleOAuthError(
            "Google OAuth state is invalid.",
            reason_code="oauth_state_invalid",
            status_code=400,
        )
    if not isinstance(user_id, str) or not user_id:
        raise GoogleOAuthError(
            "Google OAuth state is invalid.",
            reason_code="oauth_state_invalid",
            status_code=400,
        )
    return payload


def exchange_google_authorization_code(code: str) -> dict[str, Any]:
    settings = get_settings()
    _require_google_oauth_configuration()
    try:
        response = requests.post(
            settings.google_oauth_token_endpoint,
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=settings.google_oauth_http_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise GoogleOAuthError(
            "Google OAuth code exchange failed.",
            reason_code="oauth_exchange_failed",
            status_code=502,
        ) from exc
    if response.status_code >= 400:
        raise GoogleOAuthError(
            "Google OAuth code exchange failed.",
            reason_code="oauth_exchange_failed",
            status_code=502,
        )
    return _normalize_token_payload(response, require_refresh_token=True)


def refresh_google_access_token(refresh_token: str) -> dict[str, Any]:
    settings = get_settings()
    _require_google_oauth_configuration()
    if not refresh_token.strip():
        raise GoogleOAuthError(
            "Google OAuth refresh token required.",
            reason_code="oauth_refresh_token_required",
            status_code=409,
        )
    try:
        response = requests.post(
            settings.google_oauth_token_endpoint,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "grant_type": "refresh_token",
            },
            timeout=settings.google_oauth_http_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise GoogleOAuthError(
            "Google OAuth token refresh failed.",
            reason_code="oauth_refresh_failed",
            status_code=502,
        ) from exc
    if response.status_code >= 400:
        raise GoogleOAuthError(
            "Google OAuth token refresh failed.",
            reason_code="oauth_refresh_failed",
            status_code=502,
        )
    return _normalize_token_payload(response, require_refresh_token=False)


def _normalize_token_payload(response: requests.Response, *, require_refresh_token: bool) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise GoogleOAuthError(
            "Google OAuth token response is invalid.",
            reason_code="oauth_token_response_invalid",
            status_code=502,
        ) from exc
    if not isinstance(payload, dict):
        raise GoogleOAuthError(
            "Google OAuth token response is invalid.",
            reason_code="oauth_token_response_invalid",
            status_code=502,
        )

    access_token = str(payload.get("access_token", "")).strip()
    if not access_token:
        raise GoogleOAuthError(
            "Google OAuth token response is invalid.",
            reason_code="oauth_token_response_invalid",
            status_code=502,
        )

    expires_in_raw = payload.get("expires_in")
    if expires_in_raw is None:
        raise GoogleOAuthError(
            "Google OAuth token response is invalid.",
            reason_code="oauth_token_response_invalid",
            status_code=502,
        )
    try:
        expires_in = int(expires_in_raw)
    except (TypeError, ValueError) as exc:
        raise GoogleOAuthError(
            "Google OAuth token response is invalid.",
            reason_code="oauth_token_response_invalid",
            status_code=502,
        ) from exc
    if expires_in <= 0:
        raise GoogleOAuthError(
            "Google OAuth token response is invalid.",
            reason_code="oauth_token_response_invalid",
            status_code=502,
        )

    refresh_token = str(payload.get("refresh_token", "")).strip()
    if require_refresh_token and not refresh_token:
        raise GoogleOAuthError(
            "Google OAuth refresh token required.",
            reason_code="oauth_refresh_token_required",
            status_code=409,
        )

    now = int(datetime.now(UTC).timestamp())
    normalized: dict[str, Any] = {
        "access_token": access_token,
        "expires_in": expires_in,
        "expires_at": now + expires_in,
        "token_type": str(payload.get("token_type", "Bearer")),
        "scope": str(payload.get("scope", "")),
        "obtained_at": now,
    }
    if refresh_token:
        normalized["refresh_token"] = refresh_token
    return normalized


def _require_google_oauth_configuration() -> None:
    settings = get_settings()
    missing: list[str] = []
    if not settings.google_oauth_client_id.strip():
        missing.append("GOOGLE_OAUTH_CLIENT_ID")
    if not settings.google_oauth_client_secret.strip():
        missing.append("GOOGLE_OAUTH_CLIENT_SECRET")
    if not settings.google_oauth_redirect_uri.strip():
        missing.append("GOOGLE_OAUTH_REDIRECT_URI")
    if missing:
        raise GoogleOAuthError(
            f"Google OAuth is not configured: {', '.join(missing)}",
            reason_code="oauth_provider_not_configured",
            status_code=409,
        )
