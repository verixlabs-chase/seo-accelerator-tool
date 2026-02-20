from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import uuid

from app.models.provider_metric import ProviderExecutionMetric
from app.models.task_execution import TaskExecution


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["tenant_id"]


def _create_campaign(client, token: str, name: str, domain: str) -> dict:
    response = client.post(
        "/api/v1/campaigns",
        json={"name": name, "domain": domain},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()["data"]


def _insert_task_execution(db_session, *, tenant_id: str, campaign_id: str, created_at: datetime) -> str:
    row = TaskExecution(
        tenant_id=tenant_id,
        task_name="rank.schedule_window",
        status="success",
        payload_json=json.dumps({"campaign_id": campaign_id}),
        result_json="{}",
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row.id


def _insert_metric(
    db_session,
    *,
    tenant_id: str,
    task_execution_id: str,
    outcome: str,
    provider_name: str,
    capability: str,
    duration_ms: int,
    created_at: datetime,
    reason_code: str | None = None,
) -> None:
    db_session.add(
        ProviderExecutionMetric(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            sub_account_id=None,
            environment="production",
            task_execution_id=task_execution_id,
            provider_name=provider_name,
            provider_version="1.0.0",
            capability=capability,
            operation="sync",
            idempotency_key=f"idem-{uuid.uuid4()}",
            correlation_id=f"corr-{uuid.uuid4().hex[:8]}",
            attempt_number=1,
            max_attempts=3,
            duration_ms=duration_ms,
            timeout_budget_ms=1000,
            outcome=outcome,
            reason_code=reason_code,
            error_severity="warning" if outcome in {"failed", "dead_letter"} else None,
            retryable=(outcome == "retry"),
            http_status=200,
            created_at=created_at,
        )
    )
    db_session.commit()


def test_campaign_dashboard_isolation_by_campaign(client, db_session) -> None:
    token, tenant_id = _login(client, "org-admin@example.com", "pass-org-admin")
    campaign_a = _create_campaign(client, token, "A", "a.example")
    campaign_b = _create_campaign(client, token, "B", "b.example")
    now = datetime.now(UTC)

    exec_a = _insert_task_execution(db_session, tenant_id=tenant_id, campaign_id=campaign_a["id"], created_at=now)
    exec_b = _insert_task_execution(db_session, tenant_id=tenant_id, campaign_id=campaign_b["id"], created_at=now)
    _insert_metric(
        db_session,
        tenant_id=tenant_id,
        task_execution_id=exec_a,
        outcome="success",
        provider_name="google_search_console",
        capability="search_performance",
        duration_ms=100,
        created_at=now,
    )
    _insert_metric(
        db_session,
        tenant_id=tenant_id,
        task_execution_id=exec_b,
        outcome="failed",
        provider_name="google_places",
        capability="places_sync",
        duration_ms=200,
        created_at=now,
        reason_code="upstream_error",
    )

    response = client.get(
        f"/api/v1/campaigns/{campaign_a['id']}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    metrics = response.json()["data"]["metrics"]
    assert metrics["total_calls"] == 1
    assert metrics["success_count"] == 1
    assert metrics["failed_count"] == 0


def test_campaign_dashboard_cross_org_rejected(client) -> None:
    token_a, _tenant_a = _login(client, "org-admin@example.com", "pass-org-admin")
    token_b, _tenant_b = _login(client, "b@example.com", "pass-b")
    campaign_b = _create_campaign(client, token_b, "B", "b.example")

    response = client.get(
        f"/api/v1/campaigns/{campaign_b['id']}/dashboard",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 404


def test_campaign_dashboard_date_filtering(client, db_session) -> None:
    token, tenant_id = _login(client, "org-admin@example.com", "pass-org-admin")
    campaign = _create_campaign(client, token, "Date", "date.example")

    inside = datetime(2026, 2, 19, 12, 0, tzinfo=UTC)
    before = datetime(2026, 2, 17, 23, 59, tzinfo=UTC)
    after = datetime(2026, 2, 20, 0, 1, tzinfo=UTC)

    exec_inside = _insert_task_execution(db_session, tenant_id=tenant_id, campaign_id=campaign["id"], created_at=inside)
    exec_before = _insert_task_execution(db_session, tenant_id=tenant_id, campaign_id=campaign["id"], created_at=before)
    exec_after = _insert_task_execution(db_session, tenant_id=tenant_id, campaign_id=campaign["id"], created_at=after)

    _insert_metric(db_session, tenant_id=tenant_id, task_execution_id=exec_inside, outcome="success", provider_name="gsc", capability="perf", duration_ms=100, created_at=inside)
    _insert_metric(db_session, tenant_id=tenant_id, task_execution_id=exec_before, outcome="success", provider_name="gsc", capability="perf", duration_ms=120, created_at=before)
    _insert_metric(db_session, tenant_id=tenant_id, task_execution_id=exec_after, outcome="success", provider_name="gsc", capability="perf", duration_ms=140, created_at=after)

    response = client.get(
        f"/api/v1/campaigns/{campaign['id']}/dashboard",
        params={"date_from": "2026-02-18T00:00:00Z", "date_to": "2026-02-20T00:00:00Z"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["metrics"]["total_calls"] == 1


def test_campaign_dashboard_last_10_failures_pagination(client, db_session) -> None:
    token, tenant_id = _login(client, "org-admin@example.com", "pass-org-admin")
    campaign = _create_campaign(client, token, "Paging", "paging.example")
    now = datetime.now(UTC)

    for i in range(12):
        execution_id = _insert_task_execution(
            db_session,
            tenant_id=tenant_id,
            campaign_id=campaign["id"],
            created_at=now - timedelta(minutes=i),
        )
        _insert_metric(
            db_session,
            tenant_id=tenant_id,
            task_execution_id=execution_id,
            outcome="failed",
            provider_name="google_places",
            capability="places_sync",
            duration_ms=100 + i,
            created_at=now - timedelta(minutes=i),
            reason_code=f"err-{i}",
        )

    response = client.get(
        f"/api/v1/campaigns/{campaign['id']}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    metrics = response.json()["data"]["metrics"]
    assert len(metrics["last_10_failures"]) == 10
    assert metrics["last_10_failures_pagination"] == {
        "limit": 10,
        "returned": 10,
        "total_failures": 12,
        "has_more": True,
    }


def test_campaign_dashboard_empty_campaign(client) -> None:
    token, _tenant_id = _login(client, "org-admin@example.com", "pass-org-admin")
    campaign = _create_campaign(client, token, "Empty", "empty.example")

    response = client.get(
        f"/api/v1/campaigns/{campaign['id']}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    metrics = response.json()["data"]["metrics"]
    assert metrics["total_calls"] == 0
    assert metrics["success_rate_percent"] == 0.0
    assert metrics["p95_latency_ms"] is None
    assert metrics["last_10_failures"] == []


def test_campaign_dashboard_aggregation_math(client, db_session) -> None:
    token, tenant_id = _login(client, "org-admin@example.com", "pass-org-admin")
    campaign = _create_campaign(client, token, "Math", "math.example")
    now = datetime.now(UTC)

    rows = [
        ("success", "google_search_console", "search_performance", 100, None),
        ("success", "google_analytics", "analytics_sync", 110, None),
        ("retry", "google_analytics", "analytics_sync", 120, "rate_limited"),
        ("failed", "google_places", "places_sync", 130, "upstream_error"),
        ("failed", "google_places", "places_sync", 140, "timeout"),
        ("dead_letter", "google_analytics", "analytics_sync", 900, "timeout"),
    ]
    for idx, (outcome, provider, capability, latency, reason) in enumerate(rows):
        execution_id = _insert_task_execution(
            db_session,
            tenant_id=tenant_id,
            campaign_id=campaign["id"],
            created_at=now - timedelta(minutes=idx),
        )
        _insert_metric(
            db_session,
            tenant_id=tenant_id,
            task_execution_id=execution_id,
            outcome=outcome,
            provider_name=provider,
            capability=capability,
            duration_ms=latency,
            created_at=now - timedelta(minutes=idx),
            reason_code=reason,
        )

    response = client.get(
        f"/api/v1/campaigns/{campaign['id']}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    metrics = response.json()["data"]["metrics"]
    assert metrics["total_calls"] == 6
    assert metrics["success_count"] == 2
    assert metrics["retry_count"] == 1
    assert metrics["failed_count"] == 2
    assert metrics["dead_letter_count"] == 1
    assert metrics["success_rate_percent"] == 33.33
    assert metrics["p95_latency_ms"] == 900
    assert metrics["top_failing_provider"] == "google_places"
    assert metrics["top_failing_capability"] == "places_sync"
