from __future__ import annotations

import base64
import json

import pytest

from app.automation import verify_signed_automation_event
from app.core.crypto import decrypt_payload
from app.models.audit_log import AuditLog
from app.models.automation_webhook import (
    AutomationWebhookConnection,
    AutomationWebhookDelivery,
    AutomationWebhookDeliveryAttempt,
)
import app.services.automation_webhook_service as webhook_service
from app.services.automation_webhook_service import (
    AutomationWebhookError,
    validate_automation_destination,
)


MASTER_KEY_B64 = base64.b64encode(b"automation-webhook-test-key-32!!").decode("ascii")


@pytest.fixture(autouse=True)
def _automation_master_key(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["organization_id"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _connection_body(**overrides):
    body = {
        "name": "Owner report workflow",
        "provider": "zapier",
        "destination_url": "https://hooks.zapier.com/hooks/catch/123456/secret-token/",
        "event_types": ["report.ready", "action.failed"],
    }
    body.update(overrides)
    return body


@pytest.mark.parametrize(
    ("provider", "url", "host"),
    [
        (
            "zapier",
            "https://hooks.zapier.com/hooks/catch/123456/token/",
            "hooks.zapier.com",
        ),
        ("make", "https://hook.us1.make.com/abcdef", "hook.us1.make.com"),
        (
            "pipedream",
            "https://abcde.m.pipedream.net",
            "abcde.m.pipedream.net",
        ),
    ],
)
def test_destination_validation_accepts_only_known_https_webhook_hosts(
    provider: str, url: str, host: str
) -> None:
    canonical, endpoint_host = validate_automation_destination(
        provider=provider, destination_url=url
    )
    assert canonical == url
    assert endpoint_host == host


@pytest.mark.parametrize(
    ("provider", "url", "reason"),
    [
        ("zapier", "http://hooks.zapier.com/hooks/catch/1/token", "automation_destination_invalid"),
        ("zapier", "https://127.0.0.1/hooks/catch/1/token", "automation_destination_provider_mismatch"),
        ("make", "https://hook.us1.make.com@127.0.0.1/private", "automation_destination_invalid"),
        ("pipedream", "https://abcde.m.pipedream.net:8443/event", "automation_destination_invalid"),
        ("zapier", "https://hooks.zapier.com/", "automation_destination_invalid"),
        ("generic", "https://example.com/webhook", "automation_provider_not_supported"),
    ],
)
def test_destination_validation_fails_closed_for_ssrf_and_provider_mismatch(
    provider: str, url: str, reason: str
) -> None:
    with pytest.raises(AutomationWebhookError) as raised:
        validate_automation_destination(provider=provider, destination_url=url)
    assert raised.value.reason_code == reason


def test_owner_creates_encrypted_connection_and_secret_is_returned_once(
    client, db_session
) -> None:
    token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
    response = client.post(
        "/api/v1/automation/connections",
        json=_connection_body(),
        headers=_headers(token),
    )
    assert response.status_code == 201
    data = response.json()["data"]
    secret = data["signing_secret"]
    assert len(secret) >= 32
    assert data["secret_shown_once"] is True
    connection = data["connection"]
    assert connection["status"] == "pending"
    assert connection["endpoint_host"] == "hooks.zapier.com"
    assert connection["destination_url_revealed"] is False
    assert "destination_url" not in connection

    row = db_session.get(AutomationWebhookConnection, connection["id"])
    assert row is not None
    assert "secret-token" not in str(row.encrypted_config_blob)
    assert secret not in str(row.encrypted_config_blob)
    decrypted = decrypt_payload(str(row.encrypted_config_blob))
    assert decrypted["destination_url"].endswith("/secret-token/")
    assert decrypted["signing_secret"] == secret

    listed = client.get("/api/v1/automation/connections", headers=_headers(token))
    assert listed.status_code == 200
    listed_text = json.dumps(listed.json())
    assert secret not in listed_text
    assert "secret-token" not in listed_text
    assert listed.json()["data"]["automatic_actions_enabled"] is False
    assert {
        item["code"] for item in listed.json()["data"]["supported_events"]
    } == {
        "report.ready",
        "recommendation.ready",
        "action.completed",
        "action.failed",
    }
    assert "approval.requested" not in listed.json()["data"]["live_event_types"]
    assert "approval.requested" in {
        item["code"] for item in listed.json()["data"]["contract_events"]
    }

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "automation.webhook_connection.created")
        .one()
    )
    assert "secret-token" not in audit.payload_json
    assert secret not in audit.payload_json
    assert organization_id in {audit.tenant_id, row.organization_id}


def test_only_owner_can_create_test_pause_resume_recover_rotate_or_disconnect(client) -> None:
    owner_token, _ = _login(client, "org-owner@example.com", "pass-org-owner")
    created = client.post(
        "/api/v1/automation/connections",
        json=_connection_body(),
        headers=_headers(owner_token),
    ).json()["data"]
    connection_id = created["connection"]["id"]
    admin_token, _ = _login(client, "org-admin@example.com", "pass-org-admin")
    response = client.post(
        "/api/v1/automation/connections",
        json=_connection_body(),
        headers=_headers(admin_token),
    )
    assert response.status_code == 403
    assert (
        client.post(
            f"/api/v1/automation/connections/{connection_id}/test",
            headers=_headers(admin_token),
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/automation/connections/{connection_id}/rotate-secret",
            headers=_headers(admin_token),
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/automation/connections/{connection_id}/pause",
            headers=_headers(admin_token),
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/automation/connections/{connection_id}/resume",
            headers=_headers(admin_token),
        ).status_code
        == 403
    )
    missing_delivery_id = "00000000-0000-0000-0000-000000000000"
    assert (
        client.post(
            f"/api/v1/automation/deliveries/{missing_delivery_id}/recover",
            headers=_headers(admin_token),
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/api/v1/automation/connections/{connection_id}",
            headers=_headers(admin_token),
        ).status_code
        == 403
    )


def test_signed_test_delivery_records_receipt_without_exposing_destination(
    client, db_session, monkeypatch
) -> None:
    token, _ = _login(client, "org-owner@example.com", "pass-org-owner")
    created = client.post(
        "/api/v1/automation/connections",
        json=_connection_body(),
        headers=_headers(token),
    ).json()["data"]
    connection_id = created["connection"]["id"]
    signing_secret = created["signing_secret"]
    captured: dict = {}

    def _capture(*, destination_url: str, body: bytes, headers: dict[str, str]) -> int:
        captured.update(url=destination_url, body=body, headers=headers)
        return 204

    monkeypatch.setattr(webhook_service, "_post_signed_event", _capture)
    response = client.post(
        f"/api/v1/automation/connections/{connection_id}/test",
        headers=_headers(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["received_by_destination"] is True
    assert data["connection"]["status"] == "active"
    assert data["connection"]["verification_status"] == "verified"
    assert data["delivery"]["status"] == "delivered"
    assert data["delivery"]["attempt_count"] == 1
    assert data["delivery"]["attempts"][0]["response_status"] == 204

    verified = verify_signed_automation_event(
        body=captured["body"],
        headers=captured["headers"],
        signing_secret=signing_secret,
    )
    assert verified.event_type == "connection.health_changed"
    assert verified.resource.id == connection_id

    serialized = json.dumps(data)
    assert "secret-token" not in serialized
    assert signing_secret not in serialized
    assert db_session.query(AutomationWebhookDelivery).count() == 1
    assert db_session.query(AutomationWebhookDeliveryAttempt).count() == 1


def test_failed_delivery_retries_same_event_and_stops_after_success(
    client, db_session, monkeypatch
) -> None:
    token, _ = _login(client, "org-owner@example.com", "pass-org-owner")
    created = client.post(
        "/api/v1/automation/connections",
        json=_connection_body(provider="make", destination_url="https://hook.us1.make.com/abc"),
        headers=_headers(token),
    ).json()["data"]
    connection_id = created["connection"]["id"]
    statuses = iter([503, 202])
    monkeypatch.setattr(
        webhook_service,
        "_post_signed_event",
        lambda **_kwargs: next(statuses),
    )

    first = client.post(
        f"/api/v1/automation/connections/{connection_id}/test",
        headers=_headers(token),
    )
    assert first.status_code == 200
    first_delivery = first.json()["data"]["delivery"]
    assert first_delivery["status"] == "failed"
    assert first_delivery["can_retry"] is True
    assert first.json()["data"]["connection"]["status"] == "unhealthy"

    retried = client.post(
        f"/api/v1/automation/deliveries/{first_delivery['id']}/retry",
        headers=_headers(token),
    )
    assert retried.status_code == 200
    retried_delivery = retried.json()["data"]["delivery"]
    assert retried_delivery["event_id"] == first_delivery["event_id"]
    assert retried_delivery["status"] == "delivered"
    assert retried_delivery["attempt_count"] == 2
    assert len(retried_delivery["attempts"]) == 2

    duplicate = client.post(
        f"/api/v1/automation/deliveries/{first_delivery['id']}/retry",
        headers=_headers(token),
    )
    assert duplicate.status_code == 409
    assert (
        duplicate.json()["errors"][0]["details"]["reason_code"]
        == "automation_delivery_already_delivered"
    )
    assert db_session.query(AutomationWebhookDelivery).count() == 1


def test_interrupted_unattempted_delivery_can_be_recovered(
    client, db_session, monkeypatch
) -> None:
    token, _ = _login(client, "org-owner@example.com", "pass-org-owner")
    created = client.post(
        "/api/v1/automation/connections",
        json=_connection_body(),
        headers=_headers(token),
    ).json()["data"]
    connection_id = created["connection"]["id"]
    monkeypatch.setattr(webhook_service, "_post_signed_event", lambda **_kwargs: 503)
    first = client.post(
        f"/api/v1/automation/connections/{connection_id}/test",
        headers=_headers(token),
    ).json()["data"]["delivery"]
    row = db_session.get(AutomationWebhookDelivery, first["id"])
    assert row is not None
    row.status = "pending"
    row.attempt_count = 0
    row.last_attempt_at = None
    db_session.query(AutomationWebhookDeliveryAttempt).filter(
        AutomationWebhookDeliveryAttempt.delivery_id == row.id
    ).delete()
    db_session.commit()

    monkeypatch.setattr(webhook_service, "_post_signed_event", lambda **_kwargs: 202)
    recovered = client.post(
        f"/api/v1/automation/deliveries/{row.id}/retry",
        headers=_headers(token),
    )
    assert recovered.status_code == 200
    assert recovered.json()["data"]["delivery"]["status"] == "delivered"
    assert recovered.json()["data"]["delivery"]["attempt_count"] == 1


def test_rotation_replaces_secret_and_disconnect_removes_encrypted_config(
    client, db_session
) -> None:
    token, _ = _login(client, "org-owner@example.com", "pass-org-owner")
    created = client.post(
        "/api/v1/automation/connections",
        json=_connection_body(
            provider="pipedream",
            destination_url="https://abcde.m.pipedream.net/event",
        ),
        headers=_headers(token),
    ).json()["data"]
    connection_id = created["connection"]["id"]
    original_secret = created["signing_secret"]

    rotated = client.post(
        f"/api/v1/automation/connections/{connection_id}/rotate-secret",
        headers=_headers(token),
    )
    assert rotated.status_code == 200
    rotated_data = rotated.json()["data"]
    assert rotated_data["signing_secret"] != original_secret
    assert rotated_data["connection"]["signing_secret_version"] == 2
    assert rotated_data["connection"]["status"] == "pending"

    disconnected = client.delete(
        f"/api/v1/automation/connections/{connection_id}",
        headers=_headers(token),
    )
    assert disconnected.status_code == 200
    assert disconnected.json()["data"]["secrets_removed"] is True
    row = db_session.get(AutomationWebhookConnection, connection_id)
    assert row is not None
    assert row.status == "disconnected"
    assert row.encrypted_config_blob is None


def test_connection_scope_hides_other_organizations(client) -> None:
    owner_token, _ = _login(client, "org-owner@example.com", "pass-org-owner")
    created = client.post(
        "/api/v1/automation/connections",
        json=_connection_body(),
        headers=_headers(owner_token),
    ).json()["data"]
    other_token, _ = _login(client, "b@example.com", "pass-b")
    listed = client.get("/api/v1/automation/connections", headers=_headers(other_token))
    assert listed.status_code == 200
    assert listed.json()["data"]["items"] == []
    assert created["connection"]["id"] not in json.dumps(listed.json())
