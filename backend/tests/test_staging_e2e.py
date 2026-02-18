import uuid
from datetime import UTC, datetime, timedelta

from app.models.reporting import ReportSchedule
from app.models.role import Role, UserRole
from app.models.user import User
from app.tasks import tasks


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _grant_platform_admin(db_session, email: str) -> None:
    role = db_session.query(Role).filter(Role.id == "platform_admin").first()
    if role is None:
        role = Role(id="platform_admin", name="platform_admin", created_at=datetime.now(UTC))
        db_session.add(role)
        db_session.flush()
    user = db_session.query(User).filter(User.email == email).first()
    assert user is not None
    existing = db_session.query(UserRole).filter(UserRole.user_id == user.id, UserRole.role_id == role.id).first()
    if existing is None:
        db_session.add(UserRole(id=str(uuid.uuid4()), user_id=user.id, role_id=role.id, created_at=datetime.now(UTC)))
        db_session.commit()


def test_staging_e2e_campaign_flow(client, db_session):
    _grant_platform_admin(db_session, "a@example.com")
    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}

    tenant = client.post("/api/v1/tenants", json={"name": f"Staging Tenant {uuid.uuid4()}"}, headers=headers)
    assert tenant.status_code == 200
    assert tenant.json()["data"]["status"] == "Active"

    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Staging Flow Campaign", "domain": "staging-flow.example"},
        headers=headers,
    )
    assert campaign.status_code == 200
    campaign_id = campaign.json()["data"]["id"]
    tenant_id = campaign.json()["data"]["tenant_id"]
    assert campaign.json()["data"]["setup_state"] == "Draft"

    configured = client.patch(
        f"/api/v1/campaigns/{campaign_id}/setup-state",
        json={"target_state": "Configured"},
        headers=headers,
    )
    assert configured.status_code == 200
    baseline = client.patch(
        f"/api/v1/campaigns/{campaign_id}/setup-state",
        json={"target_state": "BaselineRunning"},
        headers=headers,
    )
    assert baseline.status_code == 200
    active = client.patch(
        f"/api/v1/campaigns/{campaign_id}/setup-state",
        json={"target_state": "Active"},
        headers=headers,
    )
    assert active.status_code == 200
    assert active.json()["data"]["setup_state"] == "Active"

    crawl = client.post(
        "/api/v1/crawl/schedule",
        json={"campaign_id": campaign_id, "crawl_type": "deep", "seed_url": "https://example.com"},
        headers=headers,
    )
    assert crawl.status_code == 200
    assert crawl.json()["data"]["status"] in {"scheduled", "running", "complete"}

    keyword = client.post(
        "/api/v1/rank/keywords",
        json={"campaign_id": campaign_id, "cluster_name": "Core Terms", "keyword": "staging seo", "location_code": "US"},
        headers=headers,
    )
    assert keyword.status_code == 200
    rank = client.post(
        "/api/v1/rank/schedule",
        json={"campaign_id": campaign_id, "location_code": "US"},
        headers=headers,
    )
    assert rank.status_code == 200
    assert rank.json()["data"]["snapshots_created"] >= 1

    entity = client.post("/api/v1/entity/analyze", json={"campaign_id": campaign_id}, headers=headers)
    assert entity.status_code == 200
    assert entity.json()["data"]["status"] in {"queued", "completed"}

    dashboard = client.get(f"/api/v1/dashboard?campaign_id={campaign_id}", headers=headers)
    assert dashboard.status_code == 200
    dash_data = dashboard.json()["data"]
    assert "technical_score" in dash_data
    assert "entity_score" in dash_data
    assert "recommendation_summary" in dash_data
    assert "report_status_summary" in dash_data
    assert dash_data["platform_state"] in {"Healthy", "Degraded", "Critical"}

    schedule = client.put(
        "/api/v1/reports/schedule",
        json={
            "campaign_id": campaign_id,
            "cadence": "daily",
            "timezone": "UTC",
            "next_run_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "enabled": True,
        },
        headers=headers,
    )
    assert schedule.status_code == 200
    assert schedule.json()["data"]["enabled"] is True

    processed = tasks.reporting_process_schedule.run(tenant_id=tenant_id, campaign_id=campaign_id)
    assert processed["status"] in {"success", "not_due"}

    generated = client.post(
        "/api/v1/reports/generate",
        json={"campaign_id": campaign_id, "month_number": 1},
        headers=headers,
    )
    assert generated.status_code == 200
    report_id = generated.json()["data"]["id"]

    delivered = client.post(
        f"/api/v1/reports/{report_id}/deliver",
        json={"recipient": "ops@example.com"},
        headers=headers,
    )
    assert delivered.status_code == 200
    assert delivered.json()["data"]["delivery_status"] in {"sent", "failed"}

    for response in [tenant, campaign, crawl, keyword, rank, entity, dashboard, schedule, generated, delivered]:
        payload = response.json()
        assert "meta" in payload
        assert "error" in payload


def test_staging_dashboard_reflects_schedule_failure(client, db_session, monkeypatch):
    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Failure Visibility Campaign", "domain": "failure-visibility.example"},
        headers=headers,
    )
    assert campaign.status_code == 200
    campaign_id = campaign.json()["data"]["id"]
    tenant_id = campaign.json()["data"]["tenant_id"]

    upsert = client.put(
        "/api/v1/reports/schedule",
        json={
            "campaign_id": campaign_id,
            "cadence": "daily",
            "timezone": "UTC",
            "next_run_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "enabled": True,
        },
        headers=headers,
    )
    assert upsert.status_code == 200

    def _fail(*_args, **_kwargs):
        raise RuntimeError("schedule processor down")

    monkeypatch.setattr("app.tasks.tasks.reporting_service.run_due_report_schedule", _fail)
    for _ in range(2):
        try:
            tasks.reporting_process_schedule.run(tenant_id=tenant_id, campaign_id=campaign_id)
        except RuntimeError:
            pass
    tasks.reporting_process_schedule.run(tenant_id=tenant_id, campaign_id=campaign_id)

    row = (
        db_session.query(ReportSchedule)
        .filter(ReportSchedule.tenant_id == tenant_id, ReportSchedule.campaign_id == campaign_id)
        .first()
    )
    assert row is not None
    assert row.last_status == "max_retries_exceeded"
    assert row.enabled is False

    dashboard = client.get(f"/api/v1/dashboard?campaign_id={campaign_id}", headers=headers)
    assert dashboard.status_code == 200
    data = dashboard.json()["data"]
    assert data["report_status_summary"]["schedule"]["has_failure"] is True
    assert data["platform_state"] in {"Degraded", "Critical"}
