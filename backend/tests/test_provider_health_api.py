from datetime import UTC, datetime, timedelta

from tests.conftest import create_test_campaign
from app.models.provider_health import ProviderHealthState
from app.models.provider_quota import ProviderQuotaState
from app.models.tenant import Tenant


def test_provider_health_summary_aggregation(client, db_session) -> None:
    login_res = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "pass-a"})
    assert login_res.status_code == 200
    token = login_res.json()["data"]["access_token"]
    tenant_id = login_res.json()["data"]["user"]["tenant_id"]

    tenant = db_session.query(Tenant).filter(Tenant.id == tenant_id).one()
    now = datetime.now(UTC)
    db_session.add(
        ProviderHealthState(
            tenant_id=tenant.id,
            environment="production",
            provider_name="rank",
            provider_version="1.2.0",
            capability="rank_snapshot",
            breaker_state="closed",
            consecutive_failures=0,
            success_rate_1h=0.98,
            p95_latency_ms_1h=220,
            last_error_code=None,
            last_error_at=None,
            last_success_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        ProviderQuotaState(
            tenant_id=tenant.id,
            environment="production",
            provider_name="rank",
            capability="rank_snapshot",
            window_start=now - timedelta(minutes=30),
            window_end=now + timedelta(minutes=30),
            limit_count=1000,
            used_count=123,
            remaining_count=877,
            last_exhausted_at=None,
            updated_at=now,
        )
    )
    db_session.commit()

    response = client.get(
        "/api/v1/provider-health/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["tenant_id"] == tenant.id
    assert payload["environment"] == "production"
    assert len(payload["providers"]) == 1
    row = payload["providers"][0]
    assert row["provider_name"] == "rank"
    assert row["capability"] == "rank_snapshot"
    assert row["breaker_state"] == "closed"
    assert row["consecutive_failures"] == 0
    assert row["remaining_quota"] == 877


def test_wordpress_execution_setup_rejects_cross_org_campaign_mismatch(client, db_session, create_test_org) -> None:
    login_a = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "pass-a"})
    assert login_a.status_code == 200
    token_a = login_a.json()["data"]["access_token"]
    tenant_a = login_a.json()["data"]["user"]["tenant_id"]

    login_b = client.post("/api/v1/auth/login", json={"email": "b@example.com", "password": "pass-b"})
    assert login_b.status_code == 200
    tenant_b = login_b.json()["data"]["user"]["tenant_id"]

    org_b = create_test_org(tenant_id=tenant_b, name="Provider Health Scope Org B")
    mismatched_campaign = create_test_campaign(
        db_session,
        org_b.id,
        tenant_id=tenant_a,
        name="Mismatched Provider Health Campaign",
        domain="provider-health-scope.example",
    )
    db_session.commit()

    response = client.get(
        "/api/v1/provider-health/wordpress-execution-setup",
        params={"campaign_id": mismatched_campaign.id},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 404
