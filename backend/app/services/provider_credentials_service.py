from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.crypto import CredentialCryptoError, decrypt_payload, encrypt_payload
from app.core.settings import get_settings
from app.models.organization import Organization
from app.models.organization_provider_credential import OrganizationProviderCredential
from app.models.platform_provider_credential import PlatformProviderCredential
from app.models.provider_policy import ProviderPolicy
from app.services.google_oauth_service import GOOGLE_PROVIDER_NAME, GoogleOAuthError, refresh_google_access_token


class ProviderCredentialConfigurationError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def resolve_provider_credentials(
    db: Session,
    organization_id: str,
    provider_name: str,
    *,
    required_credential_mode: str | None = None,
    require_org_oauth: bool = False,
) -> dict[str, Any]:
    policy = (
        db.query(ProviderPolicy)
        .filter(
            ProviderPolicy.organization_id == organization_id,
            ProviderPolicy.provider_name == provider_name,
        )
        .first()
    )
    credential_mode = policy.credential_mode if policy is not None else (required_credential_mode or "platform")

    platform_row = _get_platform_provider_credential_row(db, provider_name)
    org_row = _get_organization_provider_credential_row(db, organization_id, provider_name)
    selected_row: OrganizationProviderCredential | PlatformProviderCredential | None = None
    if require_org_oauth:
        if org_row is None:
            raise ProviderCredentialConfigurationError(
                f"Organization OAuth credential required for provider '{provider_name}'.",
                reason_code="org_oauth_credential_required",
                status_code=409,
            )
        if org_row.auth_mode != "oauth2":
            raise ProviderCredentialConfigurationError(
                f"Organization OAuth credential required for provider '{provider_name}'.",
                reason_code="org_oauth_credential_required",
                status_code=409,
            )
        selected_row = org_row
    elif credential_mode == "platform":
        selected_row = platform_row
    elif credential_mode == "byo_optional":
        # Prefer org credential when present so tenant-specific OAuth does not fall back to platform.
        selected_row = org_row if org_row is not None else platform_row
    elif credential_mode == "byo_required":
        if org_row is not None:
            selected_row = org_row
        else:
            raise ProviderCredentialConfigurationError(
                f"Organization credential required for provider '{provider_name}'.",
                reason_code="org_credential_required",
                status_code=409,
            )
    else:
        raise ProviderCredentialConfigurationError(
            f"Unsupported credential_mode '{credential_mode}' for provider '{provider_name}'.",
            reason_code="invalid_credential_mode",
            status_code=400,
        )

    if selected_row is None:
        return {}

    credentials = _decrypt_payload(selected_row.encrypted_secret_blob)
    if selected_row.auth_mode == "oauth2":
        credentials = _refresh_oauth2_credentials_if_needed(
            db,
            row=selected_row,
            provider_name=provider_name,
            credentials=credentials,
        )
    return credentials


def upsert_provider_policy(
    db: Session,
    *,
    organization_id: str,
    provider_name: str,
    credential_mode: str,
) -> ProviderPolicy:
    _require_organization_exists(db, organization_id)
    row = (
        db.query(ProviderPolicy)
        .filter(
            ProviderPolicy.organization_id == organization_id,
            ProviderPolicy.provider_name == provider_name,
        )
        .first()
    )
    now = datetime.now(UTC)
    if row is None:
        row = ProviderPolicy(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            provider_name=provider_name,
            credential_mode=credential_mode,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.credential_mode = credential_mode
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def upsert_organization_provider_credentials(
    db: Session,
    *,
    organization_id: str,
    provider_name: str,
    auth_mode: str,
    credentials: dict[str, Any],
) -> OrganizationProviderCredential:
    _require_organization_exists(db, organization_id)
    row = (
        db.query(OrganizationProviderCredential)
        .filter(
            OrganizationProviderCredential.organization_id == organization_id,
            OrganizationProviderCredential.provider_name == provider_name,
        )
        .first()
    )
    now = datetime.now(UTC)
    encrypted_secret_blob, key_reference, key_version = _encrypt_payload(credentials)
    if row is None:
        row = OrganizationProviderCredential(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            provider_name=provider_name,
            auth_mode=auth_mode,
            encrypted_secret_blob=encrypted_secret_blob,
            key_reference=key_reference,
            key_version=key_version,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.auth_mode = auth_mode
        row.encrypted_secret_blob = encrypted_secret_blob
        row.key_reference = key_reference
        row.key_version = key_version
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def _require_organization_exists(db: Session, organization_id: str) -> None:
    org = db.query(Organization.id).filter(Organization.id == organization_id).first()
    if org is None:
        raise ProviderCredentialConfigurationError(
            "Organization not found.",
            reason_code="organization_not_found",
            status_code=404,
        )


def upsert_platform_provider_credentials(
    db: Session,
    *,
    provider_name: str,
    auth_mode: str,
    credentials: dict[str, Any],
) -> PlatformProviderCredential:
    row = db.query(PlatformProviderCredential).filter(PlatformProviderCredential.provider_name == provider_name).first()
    now = datetime.now(UTC)
    encrypted_secret_blob, key_reference, key_version = _encrypt_payload(credentials)
    if row is None:
        row = PlatformProviderCredential(
            id=str(uuid.uuid4()),
            provider_name=provider_name,
            auth_mode=auth_mode,
            encrypted_secret_blob=encrypted_secret_blob,
            key_reference=key_reference,
            key_version=key_version,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.auth_mode = auth_mode
        row.encrypted_secret_blob = encrypted_secret_blob
        row.key_reference = key_reference
        row.key_version = key_version
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def get_organization_provider_credentials(db: Session, organization_id: str, provider_name: str) -> dict[str, Any]:
    row = _get_organization_provider_credential_row(db, organization_id, provider_name)
    if row is None:
        return {}
    return _decrypt_payload(row.encrypted_secret_blob)


def get_platform_provider_credentials(db: Session, provider_name: str) -> dict[str, Any]:
    row = _get_platform_provider_credential_row(db, provider_name)
    if row is None:
        return {}
    return _decrypt_payload(row.encrypted_secret_blob)


def _get_organization_provider_credential_row(
    db: Session,
    organization_id: str,
    provider_name: str,
) -> OrganizationProviderCredential | None:
    return (
        db.query(OrganizationProviderCredential)
        .filter(
            OrganizationProviderCredential.organization_id == organization_id,
            OrganizationProviderCredential.provider_name == provider_name,
        )
        .first()
    )


def _get_platform_provider_credential_row(db: Session, provider_name: str) -> PlatformProviderCredential | None:
    return db.query(PlatformProviderCredential).filter(PlatformProviderCredential.provider_name == provider_name).first()


def _refresh_oauth2_credentials_if_needed(
    db: Session,
    *,
    row: OrganizationProviderCredential | PlatformProviderCredential,
    provider_name: str,
    credentials: dict[str, Any],
) -> dict[str, Any]:
    if provider_name != GOOGLE_PROVIDER_NAME:
        return credentials

    settings = get_settings()
    now = int(datetime.now(UTC).timestamp())
    expires_at = _safe_int(credentials.get("expires_at"))
    access_token = str(credentials.get("access_token", "")).strip()
    if access_token and expires_at is not None and expires_at > now + settings.google_oauth_access_token_skew_seconds:
        return credentials

    refresh_token = str(credentials.get("refresh_token", "")).strip()
    if not refresh_token:
        raise ProviderCredentialConfigurationError(
            "OAuth refresh token required for provider credentials.",
            reason_code="oauth_refresh_token_required",
            status_code=409,
        )

    try:
        refreshed = refresh_google_access_token(
            refresh_token,
            organization_id=(row.organization_id if isinstance(row, OrganizationProviderCredential) else None),
            db=db,
        )
    except GoogleOAuthError as exc:
        raise ProviderCredentialConfigurationError(
            str(exc),
            reason_code=exc.reason_code,
            status_code=exc.status_code,
        ) from exc

    merged = dict(credentials)
    merged.update(refreshed)
    if not str(merged.get("refresh_token", "")).strip():
        merged["refresh_token"] = refresh_token
    if not str(merged.get("refresh_token", "")).strip():
        raise ProviderCredentialConfigurationError(
            "OAuth refresh token required for provider credentials.",
            reason_code="oauth_refresh_token_required",
            status_code=409,
        )

    encrypted_secret_blob, key_reference, key_version = _encrypt_payload(merged)
    row.encrypted_secret_blob = encrypted_secret_blob
    row.key_reference = key_reference
    row.key_version = key_version
    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return merged


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decrypt_payload(encrypted_secret_blob: str) -> dict[str, Any]:
    try:
        return decrypt_payload(encrypted_secret_blob)
    except CredentialCryptoError as exc:
        raise ProviderCredentialConfigurationError(
            str(exc),
            reason_code=exc.reason_code,
            status_code=400,
        ) from exc


def _encrypt_payload(data: dict[str, Any]) -> tuple[str, str, str]:
    try:
        return encrypt_payload(data)
    except CredentialCryptoError as exc:
        raise ProviderCredentialConfigurationError(
            str(exc),
            reason_code=exc.reason_code,
            status_code=409,
        ) from exc
