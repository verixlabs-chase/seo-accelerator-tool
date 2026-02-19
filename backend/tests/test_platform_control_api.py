import uuid
from datetime import UTC, datetime, timedelta

from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.provider_health import ProviderHealthState
from app.models.provider_quota import ProviderQuotaState
from app.models.provider_policy import ProviderPolicy


def _login(client, email: str, password: str) -> tuple[str, str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["tenant_id"], payload["user"]["id"]


def test_platform_org_routes_and_audit_mutations(client, db_session) -> None:
    token, tenant_id, _user_id = _login(client, "platform-owner@example.com", "pass-platform-owner")
    org = Organization(
        id=str(uuid.uuid4()),
        name="Platform Governance Org",
        plan_type="standard",
        billing_mode="subscription",
        status="active",
    )
    db_session.add(org)
    db_session.commit()

    list_response = client.get("/api/v1/platform/orgs", headers={"Authorization": f"Bearer {token}"})
    assert list_response.status_code == 200
    assert any(item["id"] == org.id for item in list_response.json()["data"]["items"])

    detail_response = client.get(f"/api/v1/platform/orgs/{org.id}", headers={"Authorization": f"Bearer {token}"})
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["organization"]["name"] == "Platform Governance Org"

    patch_plan = client.patch(
        f"/api/v1/platform/orgs/{org.id}/plan",
        json={"plan_type": "enterprise"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_plan.status_code == 200
    assert patch_plan.json()["data"]["organization"]["plan_type"] == "enterprise"

    patch_billing = client.patch(
        f"/api/v1/platform/orgs/{org.id}/billing",
        json={"billing_mode": "custom_contract"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_billing.status_code == 200
    assert patch_billing.json()["data"]["organization"]["billing_mode"] == "custom_contract"

    patch_status = client.patch(
        f"/api/v1/platform/orgs/{org.id}/status",
        json={"status": "suspended"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_status.status_code == 200
    assert patch_status.json()["data"]["organization"]["status"] == "suspended"

    events = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type.in_(
                [
                    "platform.org.plan.updated",
                    "platform.org.billing.updated",
                    "platform.org.status.updated",
                ]
            )
        )
        .all()
    )
    assert len(events) == 3
    assert all(event.tenant_id == org.id for event in events)
    assert tenant_id is not None


def test_platform_provider_health_summary_and_audit_feed(client, db_session) -> None:
    token, tenant_id, user_id = _login(client, "platform-admin@example.com", "pass-platform-admin")
    org = db_session.query(Organization).filter(Organization.id == tenant_id).first()
    if org is None:
        org = Organization(
            id=tenant_id,
            name="Platform Health Org",
            plan_type="enterprise",
            billing_mode="platform_sponsored",
            status="active",
        )
        db_session.add(org)
    else:
        org.name = "Platform Health Org"
        org.plan_type = "enterprise"
        org.billing_mode = "platform_sponsored"
        org.status = "active"
    now = datetime.now(UTC)
    db_session.add(
        ProviderHealthState(
            tenant_id=tenant_id,
            environment="production",
            provider_name="rank",
            provider_version="1.0.0",
            capability="rank_snapshot",
            breaker_state="closed",
            consecutive_failures=0,
            success_rate_1h=0.99,
            p95_latency_ms_1h=180,
            last_error_code=None,
            last_error_at=None,
            last_success_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        ProviderQuotaState(
            tenant_id=tenant_id,
            environment="production",
            provider_name="rank",
            capability="rank_snapshot",
            window_start=now - timedelta(minutes=20),
            window_end=now + timedelta(minutes=20),
            limit_count=1000,
            used_count=150,
            remaining_count=850,
            last_exhausted_at=None,
            updated_at=now,
        )
    )
    db_session.add(
        ProviderPolicy(
            id=str(uuid.uuid4()),
            organization_id=tenant_id,
            provider_name="dataforseo",
            credential_mode="byo_optional",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=user_id,
            event_type="platform.org.plan.updated",
            payload_json='{"organization_id":"x"}',
            created_at=now,
        )
    )
    db_session.commit()

    health_response = client.get(
        "/api/v1/platform/provider-health/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert health_response.status_code == 200
    rows = health_response.json()["data"]["items"]
    assert len(rows) == 1
    assert rows[0]["organization_id"] == tenant_id
    assert rows[0]["organization_name"] == "Platform Health Org"
    assert rows[0]["remaining_quota"] == 850

    audit_response = client.get("/api/v1/platform/audit", headers={"Authorization": f"Bearer {token}"})
    assert audit_response.status_code == 200
    items = audit_response.json()["data"]["items"]
    assert len(items) >= 1
    assert items[0]["event_type"] is not None


def test_non_platform_role_cannot_access_platform_control(client, db_session) -> None:
    token, tenant_id, _user_id = _login(client, "org-admin@example.com", "pass-org-admin")
    org = db_session.query(Organization).filter(Organization.id == tenant_id).first()
    if org is None:
        org = Organization(
            id=tenant_id,
            name="Org Admin Guard",
            plan_type="standard",
            billing_mode="subscription",
            status="active",
        )
        db_session.add(org)
    else:
        org.name = "Org Admin Guard"
        org.plan_type = "standard"
        org.billing_mode = "subscription"
        org.status = "active"
    db_session.commit()

    response = client.get("/api/v1/platform/orgs", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_platform_admin_read_only_cannot_mutate_org_metadata(client, db_session) -> None:
    token, _tenant_id, _user_id = _login(client, "platform-admin@example.com", "pass-platform-admin")
    org = Organization(
        id=str(uuid.uuid4()),
        name="Admin Readonly Org",
        plan_type="standard",
        billing_mode="subscription",
        status="active",
    )
    db_session.add(org)
    db_session.commit()

    plan_res = client.patch(
        f"/api/v1/platform/orgs/{org.id}/plan",
        json={"plan_type": "enterprise"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert plan_res.status_code == 403

    billing_res = client.patch(
        f"/api/v1/platform/orgs/{org.id}/billing",
        json={"billing_mode": "custom_contract"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert billing_res.status_code == 403

    status_res = client.patch(
        f"/api/v1/platform/orgs/{org.id}/status",
        json={"status": "suspended"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_res.status_code == 403


def test_platform_route_fails_without_platform_role_claim(client) -> None:
    token, _tenant_id, _user_id = _login(client, "a@example.com", "pass-a")
    response = client.get("/api/v1/platform/audit", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
