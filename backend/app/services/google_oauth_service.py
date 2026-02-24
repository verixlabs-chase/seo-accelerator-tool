from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import jwt
import requests  # type: ignore[import-untyped]
from sqlalchemy.orm import Session

from app.core.crypto import CredentialCryptoError, decrypt_payload, encrypt_payload
from app.core.settings import get_settings
from app.models.organization import Organization
from app.models.organization_oauth_client import OrganizationOAuthClient


GOOGLE_PROVIDER_NAME = "google"
GOOGLE_OAUTH_SCOPE_TARGET_GSC = "gsc"
GOOGLE_OAUTH_SCOPE_TARGET_GBP = "gbp"


class GoogleOAuthError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def build_google_oauth_authorization_url(
    *,
    organization_id: str,
    user_id: str,
    scope_target: str = GOOGLE_OAUTH_SCOPE_TARGET_GSC,
    db: Session | None = None,
) -> tuple[str, str]:
    settings = get_settings()
    client_id, _client_secret = _resolve_google_oauth_client_credentials(
        organization_id=organization_id,
        db=db,
    )
    state = create_google_oauth_state(organization_id=organization_id, user_id=user_id)
    redirect_uri = _build_google_oauth_redirect_uri(organization_id)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _resolve_google_oauth_scope(scope_target),
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


def exchange_google_authorization_code(*, code: str, organization_id: str, db: Session | None = None) -> dict[str, Any]:
    settings = get_settings()
    client_id, client_secret = _resolve_google_oauth_client_credentials(
        organization_id=organization_id,
        db=db,
    )
    redirect_uri = _build_google_oauth_redirect_uri(organization_id)
    try:
        response = requests.post(
            settings.google_oauth_token_endpoint,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
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


def refresh_google_access_token(
    refresh_token: str,
    *,
    organization_id: str | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    client_id, client_secret = _resolve_google_oauth_client_credentials(
        organization_id=organization_id,
        db=db,
    )
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
                "client_id": client_id,
                "client_secret": client_secret,
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


def _build_google_oauth_redirect_uri(organization_id: str) -> str:
    settings = get_settings()
    base_url = settings.public_base_url.rstrip("/")
    return f"{base_url}/api/v1/organizations/{organization_id}/providers/google/oauth/callback"


def upsert_organization_google_oauth_client(
    db: Session,
    *,
    organization_id: str,
    client_id: str,
    client_secret: str,
) -> OrganizationOAuthClient:
    if db.query(Organization.id).filter(Organization.id == organization_id).first() is None:
        raise GoogleOAuthError(
            "Organization not found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    normalized_client_id = client_id.strip()
    normalized_client_secret = client_secret.strip()
    _require_google_oauth_configuration(client_id=normalized_client_id, client_secret=normalized_client_secret)

    row = (
        db.query(OrganizationOAuthClient)
        .filter(
            OrganizationOAuthClient.organization_id == organization_id,
            OrganizationOAuthClient.provider_name == GOOGLE_PROVIDER_NAME,
        )
        .first()
    )
    now = datetime.now(UTC)
    encrypted_secret_blob, key_reference, key_version = _encrypt_payload(
        {"client_id": normalized_client_id, "client_secret": normalized_client_secret}
    )
    if row is None:
        row = OrganizationOAuthClient(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            provider_name=GOOGLE_PROVIDER_NAME,
            encrypted_secret_blob=encrypted_secret_blob,
            key_reference=key_reference,
            key_version=key_version,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.encrypted_secret_blob = encrypted_secret_blob
        row.key_reference = key_reference
        row.key_version = key_version
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def _resolve_google_oauth_client_credentials(
    *,
    organization_id: str | None = None,
    db: Session | None = None,
) -> tuple[str, str]:
    settings = get_settings()
    if db is not None and organization_id is not None:
        row = (
            db.query(OrganizationOAuthClient)
            .filter(
                OrganizationOAuthClient.organization_id == organization_id,
                OrganizationOAuthClient.provider_name == GOOGLE_PROVIDER_NAME,
            )
            .first()
        )
        if row is not None:
            payload = _decrypt_payload(row.encrypted_secret_blob)
            client_id = str(payload.get("client_id", "")).strip()
            client_secret = str(payload.get("client_secret", "")).strip()
            _require_google_oauth_configuration(client_id=client_id, client_secret=client_secret)
            return client_id, client_secret

    client_id = settings.google_oauth_client_id.strip()
    client_secret = settings.google_oauth_client_secret.strip()
    _require_google_oauth_configuration(client_id=client_id, client_secret=client_secret)
    return client_id, client_secret


def _require_google_oauth_configuration(*, client_id: str, client_secret: str) -> None:
    missing: list[str] = []
    if not client_id:
        missing.append("GOOGLE_OAUTH_CLIENT_ID")
    if not client_secret:
        missing.append("GOOGLE_OAUTH_CLIENT_SECRET")
    if missing:
        raise GoogleOAuthError(
            f"Google OAuth is not configured: {', '.join(missing)}",
            reason_code="oauth_provider_not_configured",
            status_code=409,
        )


def _resolve_google_oauth_scope(scope_target: str) -> str:
    settings = get_settings()
    normalized_target = scope_target.strip().lower()
    if normalized_target == GOOGLE_OAUTH_SCOPE_TARGET_GSC:
        return settings.google_oauth_scope_gsc
    if normalized_target == GOOGLE_OAUTH_SCOPE_TARGET_GBP:
        return settings.google_oauth_scope_gbp
    # Backward-compatible fallback for callers that still rely on the legacy single scope setting.
    return settings.google_oauth_scope


def _encrypt_payload(data: dict[str, Any]) -> tuple[str, str, str]:
    try:
        return encrypt_payload(data)
    except CredentialCryptoError as exc:
        raise GoogleOAuthError(
            str(exc),
            reason_code=exc.reason_code,
            status_code=409,
        ) from exc


def _decrypt_payload(encrypted_secret_blob: str) -> dict[str, Any]:
    try:
        return decrypt_payload(encrypted_secret_blob)
    except CredentialCryptoError:
        raise GoogleOAuthError(
            "Google OAuth client config is invalid.",
            reason_code="oauth_client_config_invalid",
            status_code=409,
        )
