from pathlib import Path
import uuid
import base64

import pytest

from app.models.organization import Organization
from app.models.organization_provider_credential import OrganizationProviderCredential
from app.models.platform_provider_credential import PlatformProviderCredential
from app.services.provider_credentials_service import upsert_organization_provider_credentials
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    upsert_platform_provider_credentials,
    upsert_provider_policy,
    resolve_provider_credentials,
)


MASTER_KEY_B64 = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii")


@pytest.fixture(autouse=True)
def _set_master_key(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)


def _create_org(
    db_session,
    *,
    name: str = "Org A",
    plan_type: str = "standard",
    billing_mode: str = "subscription",
) -> Organization:
    org = Organization(id=str(uuid.uuid4()), name=name, plan_type=plan_type, billing_mode=billing_mode)
    db_session.add(org)
    db_session.commit()
    return org


def test_resolve_platform_mode(db_session) -> None:
    org = _create_org(db_session)
    upsert_provider_policy(
        db_session,
        organization_id=org.id,
        provider_name="dataforseo",
        credential_mode="platform",
    )
    upsert_platform_provider_credentials(
        db_session,
        provider_name="dataforseo",
        auth_mode="api_key",
        credentials={"api_key": "platform-key"},
    )

    creds = resolve_provider_credentials(db_session, org.id, "dataforseo")
    assert creds == {"api_key": "platform-key"}


def test_resolve_byo_optional_with_org_credential(db_session) -> None:
    org = _create_org(db_session)
    upsert_provider_policy(
        db_session,
        organization_id=org.id,
        provider_name="dataforseo",
        credential_mode="byo_optional",
    )
    upsert_platform_provider_credentials(
        db_session,
        provider_name="dataforseo",
        auth_mode="api_key",
        credentials={"api_key": "platform-key"},
    )
    upsert_organization_provider_credentials(
        db_session,
        organization_id=org.id,
        provider_name="dataforseo",
        auth_mode="api_key",
        credentials={"api_key": "org-key"},
    )

    creds = resolve_provider_credentials(db_session, org.id, "dataforseo")
    assert creds == {"api_key": "org-key"}
    platform_row = db_session.query(PlatformProviderCredential).filter_by(provider_name="dataforseo").one()
    org_row = db_session.query(OrganizationProviderCredential).filter_by(organization_id=org.id, provider_name="dataforseo").one()
    assert "platform-key" not in platform_row.encrypted_secret_blob
    assert "org-key" not in org_row.encrypted_secret_blob


def test_resolve_byo_optional_without_org_credential(db_session) -> None:
    org = _create_org(db_session)
    upsert_provider_policy(
        db_session,
        organization_id=org.id,
        provider_name="dataforseo",
        credential_mode="byo_optional",
    )
    upsert_platform_provider_credentials(
        db_session,
        provider_name="dataforseo",
        auth_mode="api_key",
        credentials={"api_key": "platform-key"},
    )

    creds = resolve_provider_credentials(db_session, org.id, "dataforseo")
    assert creds == {"api_key": "platform-key"}


def test_resolve_byo_required_with_org_credential(db_session) -> None:
    org = _create_org(db_session)
    upsert_provider_policy(
        db_session,
        organization_id=org.id,
        provider_name="dataforseo",
        credential_mode="byo_required",
    )
    upsert_organization_provider_credentials(
        db_session,
        organization_id=org.id,
        provider_name="dataforseo",
        auth_mode="api_key",
        credentials={"api_key": "org-key"},
    )

    creds = resolve_provider_credentials(db_session, org.id, "dataforseo")
    assert creds == {"api_key": "org-key"}


def test_resolve_byo_required_without_org_credential_raises(db_session) -> None:
    org = _create_org(db_session)
    upsert_provider_policy(
        db_session,
        organization_id=org.id,
        provider_name="dataforseo",
        credential_mode="byo_required",
    )

    with pytest.raises(ProviderCredentialConfigurationError) as exc_info:
        resolve_provider_credentials(db_session, org.id, "dataforseo")
    assert exc_info.value.reason_code == "org_credential_required"


def test_resolve_without_policy_defaults_to_platform(db_session) -> None:
    org = _create_org(db_session)
    upsert_platform_provider_credentials(
        db_session,
        provider_name="dataforseo",
        auth_mode="api_key",
        credentials={"api_key": "platform-key"},
    )

    creds = resolve_provider_credentials(db_session, org.id, "dataforseo")
    assert creds == {"api_key": "platform-key"}


def test_no_hardcoded_org_name_logic_in_resolution_path() -> None:
    root = Path(__file__).resolve().parents[1]
    resolver_src = (root / "app" / "services" / "provider_credentials_service.py").read_text(encoding="utf-8").lower()
    rank_src = (root / "app" / "providers" / "rank.py").read_text(encoding="utf-8").lower()
    assert "topdog" not in resolver_src
    assert "topdog" not in rank_src


def test_credentials_are_resolved_from_runtime_db_state(db_session) -> None:
    org = _create_org(db_session)
    upsert_platform_provider_credentials(
        db_session,
        provider_name="dataforseo",
        auth_mode="api_key",
        credentials={"api_key": "platform-key-v1"},
    )
    first = resolve_provider_credentials(db_session, org.id, "dataforseo")
    assert first == {"api_key": "platform-key-v1"}

    upsert_platform_provider_credentials(
        db_session,
        provider_name="dataforseo",
        auth_mode="api_key",
        credentials={"api_key": "platform-key-v2"},
    )
    second = resolve_provider_credentials(db_session, org.id, "dataforseo")
    assert second == {"api_key": "platform-key-v2"}


def test_plaintext_never_logged_during_resolution(db_session, caplog) -> None:
    secret = "super-secret-value"
    org = _create_org(db_session)
    upsert_platform_provider_credentials(
        db_session,
        provider_name="dataforseo",
        auth_mode="api_key",
        credentials={"api_key": secret},
    )
    _ = resolve_provider_credentials(db_session, org.id, "dataforseo")
    assert secret not in caplog.text


def test_encrypt_decrypt_roundtrip_and_ciphertext_not_plaintext() -> None:
    from app.services import provider_credentials_service as svc

    plaintext = {"api_key": "roundtrip-secret"}
    encrypted_blob, _key_reference, _key_version = svc._encrypt_payload(plaintext)

    assert "roundtrip-secret" not in encrypted_blob
    decrypted = svc._decrypt_payload(encrypted_blob)
    assert decrypted == plaintext
