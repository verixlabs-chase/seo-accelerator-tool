from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

from app.models.provider_metric import ProviderExecutionMetric
from app.models.sub_account import SubAccount


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["tenant_id"]


def _create_sub_account(db_session, organization_id: str, name: str) -> SubAccount:
    now = datetime.now(UTC)
    row = SubAccount(
        organization_id=organization_id,
        name=name,
        status="active",
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
    sub_account_id: str,
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
            sub_account_id=sub_account_id,
            environment="production",
            task_execution_id=None,
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


def test_subaccount_dashboard_aggregates_metrics_last_30_days(client, db_session) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    sub = _create_sub_account(db_session, org_id, "Ops Dashboard")
    other = _create_sub_account(db_session, org_id, "Ops Other")

    now = datetime.now(UTC)
    _insert_metric(
        db_session,
        tenant_id=org_id,
        sub_account_id=sub.id,
        outcome="success",
        provider_name="google_search_console",
        capability="search_performance",
        duration_ms=100,
        created_at=now - timedelta(days=2),
    )
    _insert_metric(
        db_session,
        tenant_id=org_id,
        sub_account_id=sub.id,
        outcome="success",
        provider_name="google_search_console",
        capability="search_performance",
        duration_ms=120,
        created_at=now - timedelta(days=3),
    )
    _insert_metric(
        db_session,
        tenant_id=org_id,
        sub_account_id=sub.id,
        outcome="retry",
        provider_name="google_analytics",
        capability="analytics_sync",
        duration_ms=130,
        created_at=now - timedelta(days=4),
        reason_code="rate_limited",
    )
    _insert_metric(
        db_session,
        tenant_id=org_id,
        sub_account_id=sub.id,
        outcome="failed",
        provider_name="google_places",
        capability="places_sync",
        duration_ms=140,
        created_at=now - timedelta(days=5),
        reason_code="upstream_error",
    )
    _insert_metric(
        db_session,
        tenant_id=org_id,
        sub_account_id=sub.id,
        outcome="failed",
        provider_name="google_places",
        capability="places_sync",
        duration_ms=150,
        created_at=now - timedelta(days=6),
        reason_code="timeout",
    )
    _insert_metric(
        db_session,
        tenant_id=org_id,
        sub_account_id=sub.id,
        outcome="dead_letter",
        provider_name="google_analytics",
        capability="analytics_sync",
        duration_ms=900,
        created_at=now - timedelta(days=1),
        reason_code="timeout",
    )
    _insert_metric(
        db_session,
        tenant_id=org_id,
        sub_account_id=sub.id,
        outcome="failed",
        provider_name="google_places",
        capability="places_sync",
        duration_ms=50,
        created_at=now - timedelta(days=45),
        reason_code="stale",
    )
    _insert_metric(
        db_session,
        tenant_id=org_id,
        sub_account_id=other.id,
        outcome="failed",
        provider_name="google_places",
        capability="places_sync",
        duration_ms=300,
        created_at=now - timedelta(days=2),
        reason_code="other_subaccount",
    )

    response = client.get(
        f"/api/v1/subaccounts/{sub.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    metrics = payload["metrics"]
    assert payload["sub_account_id"] == sub.id
    assert payload["window"]["days"] == 30
    assert metrics["total_calls"] == 6
    assert metrics["success_count"] == 2
    assert metrics["retry_count"] == 1
    assert metrics["failed_count"] == 2
    assert metrics["dead_letter_count"] == 1
    assert metrics["success_rate_percent"] == 33.33
    assert metrics["p95_latency_ms"] == 900
    assert metrics["top_failing_provider"] == "google_places"
    assert metrics["top_failing_capability"] == "places_sync"
    assert len(metrics["last_10_failures"]) == 3
    assert metrics["last_10_failures"][0]["outcome"] == "dead_letter"


def test_subaccount_dashboard_limits_last_10_failures(client, db_session) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    sub = _create_sub_account(db_session, org_id, "Ops Failures")
    now = datetime.now(UTC)
    for i in range(12):
        _insert_metric(
            db_session,
            tenant_id=org_id,
            sub_account_id=sub.id,
            outcome="failed",
            provider_name="google_places",
            capability="places_sync",
            duration_ms=100 + i,
            created_at=now - timedelta(minutes=i),
            reason_code=f"err-{i}",
        )

    response = client.get(
        f"/api/v1/subaccounts/{sub.id}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    failures = response.json()["data"]["metrics"]["last_10_failures"]
    assert len(failures) == 10
    first = failures[0]["created_at"]
    last = failures[-1]["created_at"]
    assert first >= last


def test_subaccount_dashboard_rejects_cross_org_subaccount(client, db_session) -> None:
    token_a, _org_a = _login(client, "org-admin@example.com", "pass-org-admin")
    _token_b, org_b = _login(client, "b@example.com", "pass-b")
    foreign = _create_sub_account(db_session, org_b, "Foreign")

    response = client.get(
        f"/api/v1/subaccounts/{foreign.id}/dashboard",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 404


def test_subaccount_dashboard_rejects_unknown_subaccount(client) -> None:
    token, _org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    response = client.get(
        f"/api/v1/subaccounts/{uuid.uuid4()}/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
