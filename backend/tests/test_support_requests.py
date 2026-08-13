from __future__ import annotations

from datetime import UTC, datetime

from app.models.crawl import CrawlRun
from app.models.data_connection import DataConnection
from app.models.support import SupportRequest


def _login(client, email: str = "org-admin@example.com", password: str = "pass-org-admin") -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["organization_id"]


def _create_location_campaign(client, token: str, organization_id: str, *, suffix: str) -> tuple[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    location_response = client.post(
        f"/api/v1/organizations/{organization_id}/business-locations",
        headers=headers,
        json={
            "name": f"Support Location {suffix}",
            "domain": f"{suffix}.example.com",
            "city": "Reno",
            "region": "Nevada",
            "country_code": "US",
        },
    )
    assert location_response.status_code == 200
    location_id = location_response.json()["data"]["business_location"]["id"]
    campaign_response = client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={
            "name": f"Support Campaign {suffix}",
            "domain": f"{suffix}.example.com",
            "business_location_id": location_id,
        },
    )
    assert campaign_response.status_code == 200
    return location_id, campaign_response.json()["data"]["id"]


def test_customer_creates_consent_scoped_support_request(client, db_session) -> None:
    token, organization_id = _login(client)
    location_id, campaign_id = _create_location_campaign(
        client, token, organization_id, suffix="diagnostic"
    )
    db_session.add(
        DataConnection(
            tenant_id=organization_id,
            organization_id=organization_id,
            business_location_id=location_id,
            campaign_id=campaign_id,
            provider_name="google_search_console",
            external_resource_id="sc-domain:diagnostic.example.com",
            resource_scope="domain_property",
            status="failed",
            last_error_code="provider_timeout",
            last_error_message="Internal provider detail must not be copied to support bundle.",
        )
    )
    db_session.add(
        CrawlRun(
            tenant_id=organization_id,
            campaign_id=campaign_id,
            crawl_type="deep",
            status="failed",
            seed_url="https://diagnostic.example.com",
            pages_discovered=0,
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    response = client.post(
        "/api/v1/support/requests",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "category": "data_not_updating",
            "page_path": "/settings",
            "customer_summary": "My website results have not updated after reconnecting Google.",
            "campaign_id": campaign_id,
            "diagnostic_consent": True,
            "operator_access_consent": True,
        },
    )

    assert response.status_code == 200
    item = response.json()["data"]["request"]
    assert item["reference_code"].startswith("IOS-")
    assert item["status"] == "received"
    assert item["diagnostic_attached"] is True
    assert item["operator_access_expires_at"] is not None
    row = db_session.query(SupportRequest).filter(SupportRequest.id == item["id"]).one()
    assert row.diagnostic_bundle["connections"][0]["last_error_code"] == "provider_timeout"
    serialized = str(row.diagnostic_bundle).lower()
    assert "last_error_message" not in serialized
    assert "internal provider detail" not in serialized
    for prohibited in ("password", "access_token", "refresh_token", "api_key", "page_content"):
        assert prohibited not in serialized


def test_diagnostics_require_consent_and_requests_are_tenant_scoped(client, db_session) -> None:
    token_a, organization_a = _login(client)
    _location_id, campaign_id = _create_location_campaign(
        client, token_a, organization_a, suffix="no-consent"
    )
    created = client.post(
        "/api/v1/support/requests",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "category": "setup",
            "page_path": "/dashboard",
            "customer_summary": "I cannot finish the first setup checks for this location.",
            "campaign_id": campaign_id,
            "diagnostic_consent": False,
            "operator_access_consent": False,
        },
    )
    assert created.status_code == 200
    request_id = created.json()["data"]["request"]["id"]
    row = db_session.get(SupportRequest, request_id)
    assert row.diagnostic_bundle is None

    token_b, _organization_b = _login(client, "b@example.com", "pass-b")
    list_b = client.get(
        "/api/v1/support/requests",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert list_b.status_code == 200
    assert list_b.json()["data"]["items"] == []
    cross_escalation = client.post(
        f"/api/v1/support/requests/{request_id}/escalate",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"reason": "setup_blocked"},
    )
    assert cross_escalation.status_code == 404


def test_customer_can_escalate_and_platform_can_update_visible_status(client) -> None:
    token, organization_id = _login(client)
    _location_id, campaign_id = _create_location_campaign(
        client, token, organization_id, suffix="status"
    )
    created = client.post(
        "/api/v1/support/requests",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "category": "connection",
            "page_path": "/settings",
            "customer_summary": "Google reconnects but the location still shows no current data.",
            "campaign_id": campaign_id,
            "diagnostic_consent": True,
            "operator_access_consent": False,
        },
    )
    request_id = created.json()["data"]["request"]["id"]
    escalated = client.post(
        f"/api/v1/support/requests/{request_id}/escalate",
        headers={"Authorization": f"Bearer {token}"},
        json={"reason": "business_impact"},
    )
    assert escalated.status_code == 200
    assert escalated.json()["data"]["request"]["status"] == "escalated"

    platform_login = client.post(
        "/api/v1/auth/login",
        json={"email": "platform-admin@example.com", "password": "pass-platform-admin"},
    )
    platform_token = platform_login.json()["data"]["access_token"]
    updated = client.patch(
        f"/api/v1/platform/support/requests/{request_id}",
        headers={"Authorization": f"Bearer {platform_token}"},
        json={"status": "investigating", "note_code": "triage_started"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["request"]["status"] == "investigating"
    assert updated.json()["data"]["request"]["diagnostic_bundle"] is not None

    platform_queue = client.get(
        "/api/v1/platform/support/requests?status=investigating",
        headers={"Authorization": f"Bearer {platform_token}"},
    )
    assert platform_queue.status_code == 200
    queue_items = platform_queue.json()["data"]["items"]
    assert [item["id"] for item in queue_items] == [request_id]
    assert queue_items[0]["diagnostic_bundle"] is not None

    customer_list = client.get(
        "/api/v1/support/requests",
        headers={"Authorization": f"Bearer {token}"},
    )
    latest = customer_list.json()["data"]["items"][0]
    assert latest["status"] == "investigating"
    assert latest["status_history"][-1]["note_code"] == "triage_started"
