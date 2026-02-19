from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.organization_provider_credential import OrganizationProviderCredential
from app.models.platform_provider_credential import PlatformProviderCredential
from app.models.provider_policy import ProviderPolicy
from app.services.google_oauth_service import GOOGLE_PROVIDER_NAME, GoogleOAuthError, refresh_google_access_token


class ProviderCredentialConfigurationError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


_AES_GCM_NONCE_BYTES = 12


def resolve_provider_credentials(db: Session, organization_id: str, provider_name: str) -> dict[str, Any]:
    policy = (
        db.query(ProviderPolicy)
        .filter(
            ProviderPolicy.organization_id == organization_id,
            ProviderPolicy.provider_name == provider_name,
        )
        .first()
    )
    credential_mode = policy.credential_mode if policy is not None else "platform"

    platform_row = _get_platform_provider_credential_row(db, provider_name)
    org_row = _get_organization_provider_credential_row(db, organization_id, provider_name)
    selected_row: OrganizationProviderCredential | PlatformProviderCredential | None = None
    if credential_mode == "platform":
        selected_row = platform_row
    elif credential_mode == "byo_optional":
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
        refreshed = refresh_google_access_token(refresh_token)
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


def _encrypt_payload(data: dict[str, Any]) -> tuple[str, str, str]:
    plaintext = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    dek = os.urandom(32)
    payload_iv, payload_ciphertext = _aes256_gcm_encrypt(plaintext, dek)

    master_key = _get_master_key()
    dek_iv, encrypted_dek = _aes256_gcm_encrypt(dek, master_key)

    blob = {
        "alg": "AES-256-GCM",
        "ciphertext_b64": _b64e(payload_ciphertext),
        "payload_iv_b64": _b64e(payload_iv),
        "encrypted_dek_b64": _b64e(encrypted_dek),
        "dek_iv_b64": _b64e(dek_iv),
    }
    key_reference = os.getenv("CREDENTIAL_MASTER_KEY_REFERENCE", "env:PLATFORM_MASTER_KEY")
    key_version = os.getenv("CREDENTIAL_MASTER_KEY_VERSION", "v1")
    return json.dumps(blob, separators=(",", ":"), sort_keys=True), key_reference, key_version


def _decrypt_payload(encrypted_secret_blob: str) -> dict[str, Any]:
    payload = json.loads(encrypted_secret_blob)
    if not isinstance(payload, dict):
        raise ProviderCredentialConfigurationError(
            "Credential payload must be a JSON object.",
            reason_code="invalid_credential_payload",
            status_code=400,
        )
    try:
        encrypted_dek = _b64d(str(payload["encrypted_dek_b64"]))
        dek_iv = _b64d(str(payload["dek_iv_b64"]))
        payload_iv = _b64d(str(payload["payload_iv_b64"]))
        ciphertext = _b64d(str(payload["ciphertext_b64"]))
    except Exception as exc:  # noqa: BLE001
        raise ProviderCredentialConfigurationError(
            "Credential payload is not decryptable.",
            reason_code="invalid_credential_payload",
            status_code=400,
        ) from exc

    algorithm = str(payload.get("alg", "AES-256-CBC"))
    master_key = _get_master_key()
    try:
        if algorithm == "AES-256-GCM":
            dek = _aes256_gcm_decrypt(encrypted_dek, master_key, dek_iv)
            plaintext = _aes256_gcm_decrypt(ciphertext, dek, payload_iv)
        elif algorithm == "AES-256-CBC":
            dek = _aes256_cbc_decrypt(encrypted_dek, master_key, dek_iv)
            plaintext = _aes256_cbc_decrypt(ciphertext, dek, payload_iv)
        else:
            raise ProviderCredentialConfigurationError(
                f"Unsupported credential algorithm '{algorithm}'.",
                reason_code="invalid_credential_payload",
                status_code=400,
            )
    except ProviderCredentialConfigurationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ProviderCredentialConfigurationError(
            "Credential payload is not decryptable.",
            reason_code="invalid_credential_payload",
            status_code=400,
        ) from exc
    parsed = json.loads(plaintext.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ProviderCredentialConfigurationError(
            "Credential payload must be a JSON object.",
            reason_code="invalid_credential_payload",
            status_code=400,
        )
    return parsed


def _get_master_key() -> bytes:
    raw = os.getenv("PLATFORM_MASTER_KEY", "").strip()
    if not raw:
        raise ProviderCredentialConfigurationError(
            "PLATFORM_MASTER_KEY is required for credential encryption.",
            reason_code="master_key_missing",
            status_code=409,
        )
    try:
        key = base64.b64decode(raw)
    except Exception as exc:  # noqa: BLE001
        raise ProviderCredentialConfigurationError(
            "PLATFORM_MASTER_KEY must be valid base64.",
            reason_code="master_key_invalid",
            status_code=409,
        ) from exc
    if len(key) != 32:
        raise ProviderCredentialConfigurationError(
            "PLATFORM_MASTER_KEY must decode to 32 bytes for AES-256.",
            reason_code="master_key_invalid",
            status_code=409,
        )
    return key


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(raw: str) -> bytes:
    return base64.b64decode(raw.encode("ascii"))


def _aes256_gcm_encrypt(plaintext: bytes, key: bytes) -> tuple[bytes, bytes]:
    nonce = os.urandom(_AES_GCM_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return nonce, ciphertext


def _aes256_gcm_decrypt(ciphertext: bytes, key: bytes, nonce: bytes) -> bytes:
    return AESGCM(key).decrypt(nonce, ciphertext, None)


def _aes256_cbc_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    return unpadder.update(padded) + unpadder.finalize()
