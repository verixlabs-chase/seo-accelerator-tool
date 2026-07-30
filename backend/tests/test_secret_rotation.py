from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException

from app.core import crypto, security
from app.models.organization import Organization
from app.models.organization_oauth_client import OrganizationOAuthClient
from app.services.google_oauth_service import validate_google_oauth_state
from scripts.rotate_credential_master_key import rewrap_credentials


def _jwt_settings(*, active: str, previous: tuple[str, ...]) -> SimpleNamespace:
    return SimpleNamespace(
        jwt_secret=active,
        jwt_algorithm="HS256",
        jwt_verification_secrets=lambda: (active, *previous),
    )


def _master_key(byte_value: int) -> str:
    return base64.b64encode(bytes([byte_value]) * 32).decode("ascii")


def test_jwt_transition_key_accepts_old_token_and_signs_new_token(monkeypatch) -> None:
    old_secret = "old-signing-secret-with-at-least-32-characters"
    new_secret = "new-signing-secret-with-at-least-32-characters"
    now = datetime.now(UTC)
    old_token = jwt.encode(
        {
            "sub": "user-1",
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        old_secret,
        algorithm="HS256",
    )
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: _jwt_settings(active=new_secret, previous=(old_secret,)),
    )

    assert security.decode_token(old_token)["sub"] == "user-1"
    new_token = security.create_token(
        user_id="user-1",
        organization_id="org-1",
        org_role="org_admin",
        platform_role=None,
        token_type="access",
        ttl_seconds=300,
    )
    assert jwt.decode(new_token, new_secret, algorithms=["HS256"])["sub"] == "user-1"


def test_jwt_old_token_fails_after_transition_key_is_removed(monkeypatch) -> None:
    old_secret = "old-signing-secret-with-at-least-32-characters"
    new_secret = "new-signing-secret-with-at-least-32-characters"
    old_token = jwt.encode(
        {
            "sub": "user-1",
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        old_secret,
        algorithm="HS256",
    )
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: _jwt_settings(active=new_secret, previous=()),
    )

    with pytest.raises(HTTPException) as exc_info:
        security.decode_token(old_token)
    assert exc_info.value.status_code == 401


def test_google_oauth_state_accepts_transition_signing_key(monkeypatch) -> None:
    old_secret = "old-signing-secret-with-at-least-32-characters"
    new_secret = "new-signing-secret-with-at-least-32-characters"
    old_state = jwt.encode(
        {
            "type": "google_oauth_state",
            "organization_id": "org-1",
            "user_id": "user-1",
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        old_secret,
        algorithm="HS256",
    )
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: _jwt_settings(active=new_secret, previous=(old_secret,)),
    )

    assert validate_google_oauth_state(old_state)["organization_id"] == "org-1"


def test_credential_master_key_transition_rewraps_without_plaintext_loss(
    monkeypatch,
) -> None:
    old_key = _master_key(11)
    new_key = _master_key(29)
    plaintext = {"client_id": "client", "client_secret": "secret"}
    monkeypatch.setenv("PLATFORM_MASTER_KEY", old_key)
    monkeypatch.setenv("PLATFORM_PREVIOUS_MASTER_KEYS_JSON", "[]")
    old_blob, _reference, _version = crypto.encrypt_payload(plaintext)

    monkeypatch.setenv("PLATFORM_MASTER_KEY", new_key)
    monkeypatch.setenv(
        "PLATFORM_PREVIOUS_MASTER_KEYS_JSON",
        f'["{old_key}"]',
    )
    assert crypto.decrypt_payload(old_blob) == plaintext

    new_blob, _reference, _version = crypto.encrypt_payload(
        crypto.decrypt_payload(old_blob)
    )
    monkeypatch.setenv("PLATFORM_PREVIOUS_MASTER_KEYS_JSON", "[]")
    assert crypto.decrypt_payload(new_blob) == plaintext
    with pytest.raises(crypto.CredentialCryptoError):
        crypto.decrypt_payload(old_blob)


@pytest.mark.parametrize(
    "previous_keys",
    [
        lambda active, old: f'["{old}","{old}"]',
        lambda active, old: f'["{active}"]',
        lambda active, old: f'["{old}","{_master_key(12)}","{_master_key(13)}"]',
    ],
)
def test_credential_master_key_transition_rejects_ambiguous_key_sets(
    monkeypatch,
    previous_keys,
) -> None:
    active_key = _master_key(10)
    old_key = _master_key(11)
    monkeypatch.setenv("PLATFORM_MASTER_KEY", active_key)
    monkeypatch.setenv(
        "PLATFORM_PREVIOUS_MASTER_KEYS_JSON",
        previous_keys(active_key, old_key),
    )

    with pytest.raises(crypto.CredentialCryptoError) as exc_info:
        crypto.get_master_keys()
    assert exc_info.value.reason_code == "master_key_invalid"


def test_credential_rotation_dry_run_and_apply_are_transaction_safe(
    db_session,
    monkeypatch,
) -> None:
    organization_id = db_session.query(Organization.id).first()[0]
    old_key = _master_key(41)
    new_key = _master_key(73)
    plaintext = {"client_id": "client", "client_secret": "secret"}
    monkeypatch.setenv("PLATFORM_MASTER_KEY", old_key)
    monkeypatch.setenv("PLATFORM_PREVIOUS_MASTER_KEYS_JSON", "[]")
    monkeypatch.setenv("CREDENTIAL_MASTER_KEY_VERSION", "v1")
    old_blob, key_reference, key_version = crypto.encrypt_payload(plaintext)
    row = OrganizationOAuthClient(
        organization_id=organization_id,
        provider_name="rotation-test",
        encrypted_secret_blob=old_blob,
        key_reference=key_reference,
        key_version=key_version,
    )
    db_session.add(row)
    db_session.commit()

    monkeypatch.setenv("PLATFORM_MASTER_KEY", new_key)
    monkeypatch.setenv(
        "PLATFORM_PREVIOUS_MASTER_KEYS_JSON",
        f'["{old_key}"]',
    )
    monkeypatch.setenv("CREDENTIAL_MASTER_KEY_VERSION", "v2")
    dry_run = rewrap_credentials(db_session, apply_changes=False)
    db_session.refresh(row)
    assert dry_run["passed"] is True
    assert dry_run["mode"] == "dry_run"
    assert row.encrypted_secret_blob == old_blob

    applied = rewrap_credentials(db_session, apply_changes=True)
    db_session.refresh(row)
    assert applied["passed"] is True
    assert applied["mode"] == "apply"
    assert row.key_version == "v2"
    assert row.encrypted_secret_blob != old_blob

    monkeypatch.setenv("PLATFORM_PREVIOUS_MASTER_KEYS_JSON", "[]")
    assert crypto.decrypt_payload(row.encrypted_secret_blob) == plaintext
