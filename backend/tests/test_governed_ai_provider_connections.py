from __future__ import annotations

import base64
import socket

import pytest
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_payload
from app.models.governed_ai_provider_connection import GovernedAIProviderConnection
from app.models.organization import Organization
from app.models.user import User
from app.services.commercial_plan_service import (
    CommercialPlanFeatureDenied,
    apply_commercial_plan,
)
from app.services.governed_ai_provider_connection_service import (
    GovernedAIEndpointSafetyError,
    GovernedAIProviderConnectionError,
    create_provider_connection,
    disconnect_provider_connection,
    list_provider_connections,
    preflight_provider_connection,
    resolve_public_endpoint_addresses,
)


MASTER_KEY_B64 = base64.b64encode(b"governed-ai-provider-test-key!!!").decode("ascii")


@pytest.fixture(autouse=True)
def _credential_master_key(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)


def _organization_and_actor(db: Session, *, index: int = 0) -> tuple[Organization, User]:
    actors = (
        db.query(User)
        .filter(User.email.in_(("a@example.com", "b@example.com")))
        .order_by(User.email.asc())
        .all()
    )
    actor = actors[index]
    organization = db.get(Organization, actor.tenant_id)
    assert organization is not None
    return organization, actor


def _make_enterprise(db: Session, organization: Organization) -> None:
    apply_commercial_plan(
        db,
        organization_id=organization.id,
        plan_code="enterprise",
    )
    db.commit()


def _login(client, *, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_enterprise_owner_candidate_is_encrypted_and_never_activated(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    _make_enterprise(db_session, organization)

    result = create_provider_connection(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Owner model",
        endpoint_url="https://models.example.com/v1/chat/completions",
        model_identifier="local-owner-model-v1",
        api_key="secret-owner-key",
    )

    assert result["created"] is True
    assert result["routing_enabled"] is False
    assert result["automatic_activation_allowed"] is False
    item = result["item"]
    assert item["endpoint_host"] == "models.example.com"
    assert item["credential_configured"] is True
    assert item["validation_status"] == "not_tested"
    assert item["activation_status"] == "inactive"
    assert item["candidate_only"] is True
    assert "endpoint_url" not in item
    assert "api_key" not in item

    row = db_session.get(GovernedAIProviderConnection, item["id"])
    assert row is not None
    assert row.encrypted_config_blob is not None
    assert "secret-owner-key" not in row.encrypted_config_blob
    decrypted = decrypt_payload(row.encrypted_config_blob)
    assert decrypted["endpoint_url"] == "https://models.example.com/v1/chat/completions"
    assert decrypted["api_key"] == "secret-owner-key"
    assert row.automatic_activation_allowed is False


def test_solo_plan_cannot_create_private_provider(db_session: Session) -> None:
    organization, actor = _organization_and_actor(db_session)

    with pytest.raises(CommercialPlanFeatureDenied) as raised:
        create_provider_connection(
            db_session,
            organization_id=organization.id,
            actor_user_id=actor.id,
            name="Blocked model",
            endpoint_url="https://models.example.com/v1/chat/completions",
            model_identifier="blocked",
            api_key=None,
        )

    assert raised.value.reason_code == "private_ai_provider_upgrade_required"
    assert db_session.query(GovernedAIProviderConnection).count() == 0


def test_api_requires_enterprise_owner_and_redacts_secrets(client, db_session: Session) -> None:
    owner = db_session.query(User).filter(User.email == "org-owner@example.com").one()
    organization = db_session.get(Organization, owner.tenant_id)
    assert organization is not None
    _make_enterprise(db_session, organization)
    owner_token = _login(client, email="org-owner@example.com", password="pass-org-owner")
    admin_token = _login(client, email="org-admin@example.com", password="pass-org-admin")
    body = {
        "name": "API model",
        "endpoint_url": "https://models.example.com/v1/chat/completions",
        "model_identifier": "api-model-v1",
        "api_key": "api-owner-secret",
    }

    denied = client.post("/api/v1/ai/providers", json=body, headers=_headers(admin_token))
    assert denied.status_code == 403

    created = client.post("/api/v1/ai/providers", json=body, headers=_headers(owner_token))
    assert created.status_code == 201
    payload = created.json()["data"]
    assert payload["routing_enabled"] is False
    assert payload["item"]["candidate_only"] is True
    assert "api-owner-secret" not in str(payload)
    assert "/v1/chat/completions" not in str(payload)

    listed = client.get("/api/v1/ai/providers", headers=_headers(owner_token))
    assert listed.status_code == 200
    assert listed.json()["data"]["count"] == 1


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://models.example.com/v1/chat/completions",
        "https://localhost/v1/chat/completions",
        "https://127.0.0.1/v1/chat/completions",
        "https://models.example.com:8443/v1/chat/completions",
        "https://user:pass@models.example.com/v1/chat/completions",
        "https://models.example.com/v1/chat/completions?token=secret",
    ],
)
def test_candidate_endpoint_syntax_fails_closed(
    db_session: Session,
    endpoint: str,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    _make_enterprise(db_session, organization)

    with pytest.raises(GovernedAIProviderConnectionError) as raised:
        create_provider_connection(
            db_session,
            organization_id=organization.id,
            actor_user_id=actor.id,
            name="Unsafe model",
            endpoint_url=endpoint,
            model_identifier="unsafe",
            api_key="secret",
        )

    assert raised.value.reason_code == "ai_provider_endpoint_invalid"
    assert db_session.query(GovernedAIProviderConnection).count() == 0


def _dns_records(*addresses: str) -> list[tuple[object, ...]]:
    records: list[tuple[object, ...]] = []
    for address in addresses:
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        records.append(
            (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))
        )
    return records


def test_public_dns_preflight_records_only_redacted_evidence(db_session: Session) -> None:
    organization, actor = _organization_and_actor(db_session)
    _make_enterprise(db_session, organization)
    created = create_provider_connection(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Public model",
        endpoint_url="https://models.example.com/v1/chat/completions",
        model_identifier="model-v1",
        api_key="private-key",
    )

    result = preflight_provider_connection(
        db_session,
        organization_id=organization.id,
        connection_id=created["item"]["id"],
        resolver=lambda *_args, **_kwargs: _dns_records(
            "93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"
        ),
    )

    assert result["passed"] is True
    assert result["network_request_made"] is False
    assert result["routing_enabled"] is False
    assert result["item"]["network_validation_status"] == "passed"
    assert result["item"]["validation_status"] == "not_tested"
    assert "93.184.216.34" not in str(result)
    assert "private-key" not in str(result)
    row = db_session.get(GovernedAIProviderConnection, created["item"]["id"])
    assert row is not None
    assert row.resolved_address_hash is not None
    assert len(row.resolved_address_hash) == 64
    assert row.activation_status == "inactive"


@pytest.mark.parametrize(
    "addresses",
    [
        ("127.0.0.1",),
        ("10.0.0.2",),
        ("169.254.169.254",),
        ("::1",),
        ("93.184.216.34", "192.168.1.10"),
    ],
)
def test_dns_preflight_blocks_private_reserved_and_mixed_answers(
    addresses: tuple[str, ...],
) -> None:
    with pytest.raises(GovernedAIEndpointSafetyError) as raised:
        resolve_public_endpoint_addresses(
            "https://models.example.com/v1/chat/completions",
            resolver=lambda *_args, **_kwargs: _dns_records(*addresses),
        )

    assert raised.value.reason_code == "ai_provider_dns_private_or_reserved"


def test_failed_dns_preflight_is_persisted_without_network_request(db_session: Session) -> None:
    organization, actor = _organization_and_actor(db_session)
    _make_enterprise(db_session, organization)
    created = create_provider_connection(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Blocked DNS model",
        endpoint_url="https://models.example.com/v1/chat/completions",
        model_identifier="model-v1",
        api_key=None,
    )

    result = preflight_provider_connection(
        db_session,
        organization_id=organization.id,
        connection_id=created["item"]["id"],
        resolver=lambda *_args, **_kwargs: _dns_records("169.254.169.254"),
    )

    assert result["passed"] is False
    assert result["reason_code"] == "ai_provider_dns_private_or_reserved"
    assert result["network_request_made"] is False
    assert result["item"]["network_validation_status"] == "failed"
    row = db_session.get(GovernedAIProviderConnection, created["item"]["id"])
    assert row is not None
    assert row.resolved_address_hash is None
    assert row.last_validated_at is not None


def test_plan_downgrade_blocks_preflight_but_still_allows_disconnect(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    _make_enterprise(db_session, organization)
    created = create_provider_connection(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Downgraded model",
        endpoint_url="https://models.example.com/v1/chat/completions",
        model_identifier="model-v1",
        api_key=None,
    )
    apply_commercial_plan(db_session, organization_id=organization.id, plan_code="solo")
    db_session.commit()

    with pytest.raises(CommercialPlanFeatureDenied):
        preflight_provider_connection(
            db_session,
            organization_id=organization.id,
            connection_id=created["item"]["id"],
            resolver=lambda *_args, **_kwargs: _dns_records("93.184.216.34"),
        )

    disconnected = disconnect_provider_connection(
        db_session,
        organization_id=organization.id,
        connection_id=created["item"]["id"],
        actor_user_id=actor.id,
    )
    assert disconnected["disconnected"] is True


def test_list_is_organization_scoped_and_redacted(db_session: Session) -> None:
    organization_a, actor_a = _organization_and_actor(db_session, index=0)
    organization_b, actor_b = _organization_and_actor(db_session, index=1)
    _make_enterprise(db_session, organization_a)
    _make_enterprise(db_session, organization_b)
    create_provider_connection(
        db_session,
        organization_id=organization_a.id,
        actor_user_id=actor_a.id,
        name="A model",
        endpoint_url="https://a-models.example.com/v1/chat/completions",
        model_identifier="a-v1",
        api_key="a-secret",
    )
    create_provider_connection(
        db_session,
        organization_id=organization_b.id,
        actor_user_id=actor_b.id,
        name="B model",
        endpoint_url="https://b-models.example.com/v1/chat/completions",
        model_identifier="b-v1",
        api_key="b-secret",
    )

    result = list_provider_connections(db_session, organization_id=organization_a.id)

    assert result["count"] == 1
    assert result["items"][0]["name"] == "A model"
    assert result["truth"]["state"] == "candidate_only"
    serialized = str(result)
    assert "a-secret" not in serialized
    assert "b-secret" not in serialized
    assert "/v1/chat/completions" not in serialized


def test_duplicate_name_is_idempotency_safe_conflict(db_session: Session) -> None:
    organization, actor = _organization_and_actor(db_session)
    _make_enterprise(db_session, organization)
    kwargs = {
        "organization_id": organization.id,
        "actor_user_id": actor.id,
        "name": "Duplicate model",
        "endpoint_url": "https://models.example.com/v1/chat/completions",
        "model_identifier": "model-v1",
        "api_key": None,
    }
    create_provider_connection(db_session, **kwargs)

    with pytest.raises(GovernedAIProviderConnectionError) as raised:
        create_provider_connection(db_session, **kwargs)

    assert raised.value.reason_code == "ai_provider_name_conflict"
    assert db_session.query(GovernedAIProviderConnection).count() == 1


def test_disconnect_erases_encrypted_configuration(db_session: Session) -> None:
    organization, actor = _organization_and_actor(db_session)
    _make_enterprise(db_session, organization)
    created = create_provider_connection(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Disposable model",
        endpoint_url="https://models.example.com/v1/chat/completions",
        model_identifier="model-v1",
        api_key="erase-me",
    )
    apply_commercial_plan(
        db_session,
        organization_id=organization.id,
        plan_code="solo",
    )
    db_session.commit()

    result = disconnect_provider_connection(
        db_session,
        organization_id=organization.id,
        connection_id=created["item"]["id"],
        actor_user_id=actor.id,
    )

    assert result["disconnected"] is True
    row = db_session.get(GovernedAIProviderConnection, created["item"]["id"])
    assert row is not None
    assert row.status == "disconnected"
    assert row.encrypted_config_blob is None
    assert row.key_reference is None
    assert row.key_version is None
    assert row.credential_configured is False
    assert list_provider_connections(db_session, organization_id=organization.id)["count"] == 0
