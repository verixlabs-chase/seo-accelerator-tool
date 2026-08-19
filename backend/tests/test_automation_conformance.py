from __future__ import annotations

from datetime import UTC, datetime
import hashlib

import pytest

from app.automation import (
    AUTOMATION_CONFORMANCE_VERSION,
    AutomationContractError,
    automation_provider_conformance_kit,
    verify_signed_automation_event,
)


PROVIDERS = frozenset({"zapier", "make", "pipedream", "n8n"})
FIXTURE_TIME = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("provider", sorted(PROVIDERS))
def test_provider_conformance_kit_has_one_deterministic_signed_fixture(
    provider: str,
) -> None:
    first = automation_provider_conformance_kit(
        provider=provider,
        supported_provider_codes=PROVIDERS,
    )
    second = automation_provider_conformance_kit(
        provider=provider,
        supported_provider_codes=PROVIDERS,
    )

    assert first == second
    assert first["version"] == AUTOMATION_CONFORMANCE_VERSION
    assert first["provider"] == provider
    assert first["test_only"] is True
    assert first["cannot_enable_live_delivery"] is True
    assert first["expected"]["external_mutation_expected"] is False
    assert first["safety"]["contains_customer_data"] is False
    assert first["safety"]["contains_live_credentials"] is False

    request = first["request"]
    body = request["exact_raw_body"].encode("utf-8")
    assert hashlib.sha256(body).hexdigest() == first["expected"]["body_sha256"]
    event = verify_signed_automation_event(
        body=body,
        headers=request["headers"],
        signing_secret=first["fixture_signing_secret"],
        now=FIXTURE_TIME,
    )
    assert event.event_id == first["expected"]["event_id"]
    assert event.event_type == "connection.health_changed"


def test_conformance_fixture_proves_tamper_rejection_and_provider_validation() -> None:
    kit = automation_provider_conformance_kit(
        provider="make",
        supported_provider_codes=PROVIDERS,
    )
    request = kit["request"]
    body = request["exact_raw_body"].encode("utf-8")

    with pytest.raises(AutomationContractError) as raised:
        verify_signed_automation_event(
            body=body.replace(b"Synthetic test only", b"Publish customer data"),
            headers=request["headers"],
            signing_secret=kit["fixture_signing_secret"],
            now=FIXTURE_TIME,
        )
    assert raised.value.reason_code == "automation_event_signature_invalid"

    with pytest.raises(ValueError, match="Unsupported"):
        automation_provider_conformance_kit(
            provider="generic",
            supported_provider_codes=PROVIDERS,
        )


def test_every_provider_uses_the_same_event_bytes_and_signature() -> None:
    kits = [
        automation_provider_conformance_kit(
            provider=provider,
            supported_provider_codes=PROVIDERS,
        )
        for provider in sorted(PROVIDERS)
    ]

    assert len({kit["request"]["exact_raw_body"] for kit in kits}) == 1
    assert len({kit["expected"]["signature"] for kit in kits}) == 1
    assert len({kit["provider_paths"]["payload"] for kit in kits}) == 4


def test_authenticated_customer_can_download_only_supported_conformance_kit(client) -> None:
    anonymous = client.get("/api/v1/automation/conformance/zapier")
    assert anonymous.status_code == 401

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "org-owner@example.com", "password": "pass-org-owner"},
    )
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/automation/conformance/zapier", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider"] == "zapier"
    assert data["test_only"] is True
    assert data["request"]["headers"]["X-InsightOS-Signature"].startswith("v1=")

    unsupported = client.get(
        "/api/v1/automation/conformance/generic", headers=headers
    )
    assert unsupported.status_code == 404
    assert unsupported.json()["errors"][0]["details"]["reason_code"] == (
        "automation_provider_not_supported"
    )


def test_connector_catalog_separates_compatibility_from_customer_connection(client) -> None:
    anonymous = client.get("/api/v1/automation/connector-catalog")
    assert anonymous.status_code == 401

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "org-owner@example.com", "password": "pass-org-owner"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    response = client.get("/api/v1/automation/connector-catalog", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["version"] == "insightos.automation.connectors.v1"
    assert data["truth"]["state"] == "compatibility_only"
    assert [item["code"] for item in data["items"]] == [
        "zapier",
        "make",
        "n8n",
        "pipedream",
        "https",
    ]
    assert all(item["production_connection_proven"] is False for item in data["items"])
    assert all(item["customer_connection_required"] is True for item in data["items"])
    assert (
        next(item for item in data["items"] if item["code"] == "n8n")[
            "starter_available"
        ]
        is True
    )
    assert all(
        item["starter_available"] is False
        for item in data["items"]
        if item["code"] != "n8n"
    )
