from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.provider_metric import ProviderExecutionMetric
from app.models.sub_account import SubAccount


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["tenant_id"]


def _create_sub_account(db_session, organization_id: str, name: str, status: str = "active") -> SubAccount:
    now = datetime.now(UTC)
    row = SubAccount(
        organization_id=organization_id,
        name=name,
        status=status,
        created_at=now,
        updated_at=now,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _insert_metric(
    db_session,
    *,
    tenant_id: str,
    created_at: datetime,
    provider_name: str = "google_search_console",
    capability: str = "search_performance",
    outcome: str = "success",
    sub_account_id: str | None = None,
    suffix: str = "",
) -> None:
    db_session.add(
        ProviderExecutionMetric(
            tenant_id=tenant_id,
            sub_account_id=sub_account_id,
            environment="production",
            task_execution_id=None,
            provider_name=provider_name,
            provider_version="1.0.0",
            capability=capability,
            operation="sync",
            idempotency_key=f"idem-{tenant_id}-{suffix}",
            correlation_id=None,
            attempt_number=1,
            max_attempts=3,
            duration_ms=150,
            timeout_budget_ms=1000,
            outcome=outcome,
            reason_code=None,
            error_severity=None,
            retryable=False,
            http_status=200,
            created_at=created_at,
        )
    )
    db_session.commit()


def test_provider_metrics_org_isolation_enforced(client, db_session) -> None:
    token_a, org_a = _login(client, "a@example.com", "pass-a")
    _token_b, org_b = _login(client, "b@example.com", "pass-b")
    now = datetime.now(UTC)
    _insert_metric(db_session, tenant_id=org_a, created_at=now, suffix="a1")
    _insert_metric(db_session, tenant_id=org_b, created_at=now + timedelta(seconds=1), suffix="b1")

    response = client.get(
        "/api/v1/provider-metrics",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["pagination"]["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["tenant_id"] == org_a


def test_provider_metrics_sub_account_filtering(client, db_session) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    sub_a = _create_sub_account(db_session, org_id, "Ops A")
    sub_b = _create_sub_account(db_session, org_id, "Ops B")
    now = datetime.now(UTC)
    _insert_metric(db_session, tenant_id=org_id, sub_account_id=sub_a.id, created_at=now, suffix="sa")
    _insert_metric(db_session, tenant_id=org_id, sub_account_id=sub_b.id, created_at=now + timedelta(seconds=1), suffix="sb")
    _insert_metric(db_session, tenant_id=org_id, sub_account_id=None, created_at=now + timedelta(seconds=2), suffix="none")

    response = client.get(
        f"/api/v1/provider-metrics?sub_account_id={sub_a.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["sub_account_id"] == sub_a.id


def test_provider_metrics_date_range_filtering(client, db_session) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    start = datetime(2026, 2, 18, 0, 0, 0, tzinfo=UTC)
    inside = datetime(2026, 2, 19, 12, 0, 0, tzinfo=UTC)
    end = datetime(2026, 2, 20, 0, 0, 0, tzinfo=UTC)
    _insert_metric(db_session, tenant_id=org_id, created_at=start - timedelta(minutes=1), suffix="before")
    _insert_metric(db_session, tenant_id=org_id, created_at=inside, suffix="inside")
    _insert_metric(db_session, tenant_id=org_id, created_at=end + timedelta(minutes=1), suffix="after")

    response = client.get(
        "/api/v1/provider-metrics",
        params={"date_from": start.isoformat(), "date_to": end.isoformat()},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["pagination"]["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["created_at"].startswith("2026-02-19T12:00:00")


def test_provider_metrics_pagination(client, db_session) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    base = datetime(2026, 2, 20, 0, 0, 0, tzinfo=UTC)
    _insert_metric(db_session, tenant_id=org_id, created_at=base + timedelta(seconds=1), suffix="1")
    _insert_metric(db_session, tenant_id=org_id, created_at=base + timedelta(seconds=2), suffix="2")
    _insert_metric(db_session, tenant_id=org_id, created_at=base + timedelta(seconds=3), suffix="3")

    response = client.get(
        "/api/v1/provider-metrics?limit=2&offset=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["pagination"] == {"limit": 2, "offset": 1, "returned": 2, "total": 3, "has_more": False}
    assert len(payload["items"]) == 2
    assert payload["items"][0]["idempotency_key"].endswith("-2")
    assert payload["items"][1]["idempotency_key"].endswith("-1")


def test_provider_metrics_rejects_invalid_sub_account_id(client) -> None:
    token, _org_id = _login(client, "org-admin@example.com", "pass-org-admin")

    response = client.get(
        "/api/v1/provider-metrics?sub_account_id=sub-does-not-exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    details = response.json()["errors"][0]["details"]
    assert details["reason_code"] == "invalid_sub_account_id"


def test_provider_metrics_rejects_cross_org_sub_account(client, db_session) -> None:
    token_a, _org_a = _login(client, "org-admin@example.com", "pass-org-admin")
    _token_b, org_b = _login(client, "b@example.com", "pass-b")
    foreign_sub_account = _create_sub_account(db_session, org_b, "Foreign")

    response = client.get(
        f"/api/v1/provider-metrics?sub_account_id={foreign_sub_account.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 403
    details = response.json()["errors"][0]["details"]
    assert details["reason_code"] == "sub_account_scope_mismatch"
