from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.customer_status import CustomerStatusUpdate


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _body(*, state: str = "investigating", message: str | None = None) -> dict:
    now = datetime.now(UTC)
    return {
        "incident_key": "reports-delayed-2026-08",
        "state": state,
        "impact": "major" if state != "resolved" else "none",
        "title": "Some reports are taking longer",
        "message": message
        or "We are working to restore normal report delivery. Saved customer work is not affected.",
        "affected_surfaces": ["reports", "dashboard"],
        "visible_to_customers": True,
        "starts_at": (now - timedelta(minutes=30)).isoformat(),
        "ends_at": now.isoformat() if state == "resolved" else None,
    }


def test_owner_publishes_idempotent_customer_safe_status_and_customer_reads_it(
    client, db_session
) -> None:
    owner_token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    customer_token = _login(client, "org-admin@example.com", "pass-org-admin")
    body = _body()

    first = client.post(
        "/api/v1/system/customer-status",
        json=body,
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert first.status_code == 200
    assert first.json()["data"]["created"] is True
    assert first.json()["data"]["update"]["update_number"] == 1

    repeat = client.post(
        "/api/v1/system/customer-status",
        json=body,
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert repeat.status_code == 200
    assert repeat.json()["data"]["created"] is False
    assert db_session.query(CustomerStatusUpdate).count() == 1

    response = client.get(
        "/api/v1/status/summary",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["state"] == "degraded"
    assert payload["incidents"][0]["title"] == body["title"]
    assert payload["incidents"][0]["affected_surfaces"] == [
        {"code": "dashboard", "label": "Overview"},
        {"code": "reports", "label": "Reports"},
    ]
    serialized = str(payload).lower()
    assert "created_by" not in serialized
    assert "content_digest" not in serialized
    assert "provider" not in serialized


def test_public_resolution_removes_active_notice_but_preserves_platform_history(client) -> None:
    owner_token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    admin_token = _login(client, "platform-admin@example.com", "pass-platform-admin")
    customer_token = _login(client, "org-admin@example.com", "pass-org-admin")

    assert client.post(
        "/api/v1/system/customer-status",
        json=_body(),
        headers={"Authorization": f"Bearer {owner_token}"},
    ).status_code == 200
    resolved = client.post(
        "/api/v1/system/customer-status",
        json=_body(
            state="resolved",
            message="Report delivery has returned to normal. No customer action is needed.",
        ),
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["data"]["update"]["update_number"] == 2

    customer = client.get(
        "/api/v1/status/summary",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert customer.status_code == 200
    assert customer.json()["data"]["state"] == "operational"
    assert customer.json()["data"]["incidents"] == []

    history = client.get(
        "/api/v1/system/customer-status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert history.status_code == 200
    assert [item["state"] for item in history.json()["data"]["updates"]] == [
        "resolved",
        "investigating",
    ]


def test_status_write_is_owner_only_and_rejects_internal_supplier_copy(client) -> None:
    owner_token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    admin_token = _login(client, "platform-admin@example.com", "pass-platform-admin")
    customer_token = _login(client, "org-admin@example.com", "pass-org-admin")
    body = _body()

    assert client.post(
        "/api/v1/system/customer-status",
        json=body,
        headers={"Authorization": f"Bearer {admin_token}"},
    ).status_code == 403
    assert client.post(
        "/api/v1/system/customer-status",
        json=body,
        headers={"Authorization": f"Bearer {customer_token}"},
    ).status_code == 403

    rejected = client.post(
        "/api/v1/system/customer-status",
        json=_body(message="The Stripe webhook returned an internal error and we are investigating it."),
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert rejected.status_code == 400
    assert (
        rejected.json()["errors"][0]["details"]["reason_code"]
        == "customer_status_sensitive_copy_rejected"
    )


def test_future_maintenance_is_a_notice_not_a_current_degradation(client) -> None:
    owner_token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    customer_token = _login(client, "org-admin@example.com", "pass-org-admin")
    now = datetime.now(UTC)
    body = {
        "incident_key": "planned-report-maintenance-2026-08",
        "state": "maintenance",
        "impact": "major",
        "title": "Planned report maintenance",
        "message": "Report creation will pause briefly. Saved reports and account access will remain available.",
        "affected_surfaces": ["reports"],
        "visible_to_customers": True,
        "starts_at": (now + timedelta(days=1)).isoformat(),
        "ends_at": (now + timedelta(days=1, hours=1)).isoformat(),
    }
    created = client.post(
        "/api/v1/system/customer-status",
        json=body,
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert created.status_code == 200

    summary = client.get(
        "/api/v1/status/summary",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert summary.status_code == 200
    assert summary.json()["data"]["state"] == "notice"
    assert summary.json()["data"]["incidents"][0]["state"] == "maintenance"
