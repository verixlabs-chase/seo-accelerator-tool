from __future__ import annotations

import base64
import json
import socket

import httpcore
import httpx
import pytest
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_payload
from app.models.audit_log import AuditLog
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
    GovernedAIProviderTransportError,
    ProviderValidationHTTPResult,
    _PinnedHTTPTransport,
    _PinnedNetworkBackend,
    create_provider_connection,
    disconnect_provider_connection,
    list_provider_connections,
    preflight_provider_connection,
    resolve_public_endpoint_addresses,
    validate_provider_connection,
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


def test_validation_api_is_owner_only_and_keeps_candidate_inactive(
    client,
    db_session: Session,
    monkeypatch,
) -> None:
    owner = db_session.query(User).filter(User.email == "org-owner@example.com").one()
    organization = db_session.get(Organization, owner.tenant_id)
    assert organization is not None
    _make_enterprise(db_session, organization)
    created = create_provider_connection(
        db_session,
        organization_id=organization.id,
        actor_user_id=owner.id,
        name="API validation model",
        endpoint_url="https://models.example.com/v1/chat/completions",
        model_identifier="api-model-v1",
        api_key="api-validation-secret",
    )
    owner_token = _login(client, email="org-owner@example.com", password="pass-org-owner")
    admin_token = _login(client, email="org-admin@example.com", password="pass-org-admin")

    monkeypatch.setattr(
        "app.api.v1.governed_ai_providers.validate_provider_connection",
        lambda _db, **_kwargs: {
            "passed": True,
            "item": {
                **created["item"],
                "validation_status": "passed",
                "activation_status": "inactive",
            },
            "network_request_made": True,
            "routing_enabled": False,
            "automatic_activation_allowed": False,
        },
    )

    denied = client.post(
        f"/api/v1/ai/providers/{created['item']['id']}/validate",
        headers=_headers(admin_token),
    )
    assert denied.status_code == 403
    validated = client.post(
        f"/api/v1/ai/providers/{created['item']['id']}/validate",
        headers=_headers(owner_token),
    )
    assert validated.status_code == 200
    payload = validated.json()["data"]
    assert payload["passed"] is True
    assert payload["routing_enabled"] is False
    assert payload["item"]["activation_status"] == "inactive"
    assert "api-validation-secret" not in str(payload)


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


def _valid_connection_response(*, elapsed_ms: int = 125) -> ProviderValidationHTTPResult:
    content = json.dumps(
        {"ok": True, "marker": "insightos_provider_validation_v1"},
        separators=(",", ":"),
    )
    return ProviderValidationHTTPResult(
        status_code=200,
        headers={"content-type": "application/json"},
        body=json.dumps(
            {"choices": [{"message": {"content": content}}]},
            separators=(",", ":"),
        ).encode("utf-8"),
        elapsed_ms=elapsed_ms,
    )


def test_pinned_connection_validation_passes_without_activation_or_secret_evidence(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    _make_enterprise(db_session, organization)
    created = create_provider_connection(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Validated model",
        endpoint_url="https://models.example.com/v1/chat/completions",
        model_identifier="model-v1",
        api_key="private-validation-key",
    )
    captured: dict[str, object] = {}

    def _sender(**kwargs) -> ProviderValidationHTTPResult:
        captured.update(kwargs)
        return _valid_connection_response()

    result = validate_provider_connection(
        db_session,
        organization_id=organization.id,
        connection_id=created["item"]["id"],
        actor_user_id=actor.id,
        resolver=lambda *_args, **_kwargs: _dns_records("93.184.216.34"),
        request_sender=_sender,
    )

    assert result["passed"] is True
    assert result["network_request_made"] is True
    assert result["routing_enabled"] is False
    assert result["automatic_activation_allowed"] is False
    assert result["item"]["validation_status"] == "passed"
    assert result["item"]["last_validation_latency_ms"] == 125
    assert result["item"]["validation_schema_version"] == (
        "openai-compatible-connection-v1"
    )
    assert "validation_evidence_hash" not in result["item"]
    assert captured["approved_addresses"] == ("93.184.216.34",)
    assert captured["api_key"] == "private-validation-key"
    serialized = str(result)
    assert "private-validation-key" not in serialized
    assert "93.184.216.34" not in serialized
    assert "/v1/chat/completions" not in serialized

    row = db_session.get(GovernedAIProviderConnection, created["item"]["id"])
    assert row is not None
    assert row.validation_evidence_hash is not None
    assert len(row.validation_evidence_hash) == 64
    assert row.activation_status == "inactive"
    assert row.automatic_activation_allowed is False
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "ai.provider_connection.validation_passed")
        .one()
    )
    assert "private-validation-key" not in audit.payload_json
    assert "93.184.216.34" not in audit.payload_json
    assert "/v1/chat/completions" not in audit.payload_json


@pytest.mark.parametrize(
    ("response", "reason_code"),
    [
        (
            ProviderValidationHTTPResult(
                status_code=302,
                headers={"location": "https://other.example.com/v1/chat/completions"},
                body=b"",
                elapsed_ms=8,
            ),
            "ai_provider_redirect_blocked",
        ),
        (
            ProviderValidationHTTPResult(
                status_code=401,
                headers={"content-type": "application/json"},
                body=b"{}",
                elapsed_ms=9,
            ),
            "ai_provider_authentication_failed",
        ),
        (
            ProviderValidationHTTPResult(
                status_code=200,
                headers={"content-type": "text/html"},
                body=b"<html>not a model response</html>",
                elapsed_ms=10,
            ),
            "ai_provider_schema_incompatible",
        ),
    ],
)
def test_connection_validation_fails_closed_on_redirect_auth_and_schema(
    db_session: Session,
    response: ProviderValidationHTTPResult,
    reason_code: str,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    _make_enterprise(db_session, organization)
    created = create_provider_connection(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name=f"Failure {reason_code}",
        endpoint_url="https://models.example.com/v1/chat/completions",
        model_identifier="model-v1",
        api_key=None,
    )

    result = validate_provider_connection(
        db_session,
        organization_id=organization.id,
        connection_id=created["item"]["id"],
        actor_user_id=actor.id,
        resolver=lambda *_args, **_kwargs: _dns_records("93.184.216.34"),
        request_sender=lambda **_kwargs: response,
    )

    assert result["passed"] is False
    assert result["reason_code"] == reason_code
    assert result["item"]["validation_status"] == "failed"
    assert result["item"]["activation_status"] == "inactive"
    row = db_session.get(GovernedAIProviderConnection, created["item"]["id"])
    assert row is not None
    assert row.validation_evidence_hash is None


def test_connection_validation_blocks_dns_before_sender(db_session: Session) -> None:
    organization, actor = _organization_and_actor(db_session)
    _make_enterprise(db_session, organization)
    created = create_provider_connection(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Blocked transport model",
        endpoint_url="https://models.example.com/v1/chat/completions",
        model_identifier="model-v1",
        api_key=None,
    )
    called = False

    def _sender(**_kwargs) -> ProviderValidationHTTPResult:
        nonlocal called
        called = True
        return _valid_connection_response()

    result = validate_provider_connection(
        db_session,
        organization_id=organization.id,
        connection_id=created["item"]["id"],
        actor_user_id=actor.id,
        resolver=lambda *_args, **_kwargs: _dns_records(
            "93.184.216.34", "169.254.169.254"
        ),
        request_sender=_sender,
    )

    assert result["passed"] is False
    assert result["network_request_made"] is False
    assert called is False


def test_connection_validation_records_bounded_transport_failure(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    _make_enterprise(db_session, organization)
    created = create_provider_connection(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Oversized model",
        endpoint_url="https://models.example.com/v1/chat/completions",
        model_identifier="model-v1",
        api_key=None,
    )

    def _sender(**_kwargs) -> ProviderValidationHTTPResult:
        raise GovernedAIProviderTransportError(
            "too large", reason_code="ai_provider_response_too_large"
        )

    result = validate_provider_connection(
        db_session,
        organization_id=organization.id,
        connection_id=created["item"]["id"],
        actor_user_id=actor.id,
        resolver=lambda *_args, **_kwargs: _dns_records("93.184.216.34"),
        request_sender=_sender,
    )

    assert result["passed"] is False
    assert result["reason_code"] == "ai_provider_response_too_large"
    assert result["network_request_made"] is True
    assert result["item"]["activation_status"] == "inactive"


def test_pinned_backend_connects_only_to_the_approved_address() -> None:
    calls: list[tuple[str, int]] = []
    stream = object()

    class _Backend:
        def connect_tcp(self, host: str, port: int, **_kwargs):
            calls.append((host, port))
            return stream

    backend = _PinnedNetworkBackend(
        expected_hostname="models.example.com",
        approved_addresses=("93.184.216.34",),
        backend=_Backend(),  # type: ignore[arg-type]
    )

    connected = backend.connect_tcp("models.example.com", 443)

    assert connected is stream
    assert calls == [("93.184.216.34", 443)]
    with pytest.raises(httpcore.ConnectError):
        backend.connect_tcp("redirect.example.com", 443)


def test_pinned_transport_enforces_response_size_limit() -> None:
    class _Pool:
        def handle_request(self, _request):
            return httpcore.Response(
                200,
                headers=[(b"content-type", b"application/json")],
                content=[b"12345", b"67890"],
            )

        def close(self) -> None:
            return None

    transport = _PinnedHTTPTransport(
        hostname="models.example.com",
        approved_addresses=("93.184.216.34",),
        max_response_bytes=8,
    )
    transport._pool.close()
    transport._pool = _Pool()  # type: ignore[assignment]
    request = httpx.Request(
        "POST",
        "https://models.example.com/v1/chat/completions",
        content=b"{}",
    )

    with pytest.raises(GovernedAIProviderTransportError) as raised:
        transport.handle_request(request)

    assert raised.value.reason_code == "ai_provider_response_too_large"


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
