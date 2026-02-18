from datetime import UTC, datetime, timedelta

from app.models.reporting import ReportSchedule
from app.tasks import tasks


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _create_campaign(client, token, name="Cohesion Campaign", domain="cohesion.example") -> dict:
    response = client.post(
        "/api/v1/campaigns",
        json={"name": name, "domain": domain},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_recommendation_summary_endpoint(client):
    token = _login(client, "a@example.com", "pass-a")
    campaign = _create_campaign(client, token, name="Summary Campaign", domain="summary.example")
    recs = client.get(
        f"/api/v1/intelligence/recommendations?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert recs.status_code == 200

    summary = client.get(
        f"/api/v1/recommendations/summary?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert summary.status_code == 200
    payload = summary.json()["data"]
    assert payload["campaign_id"] == campaign["id"]
    assert payload["total_count"] >= 1
    assert isinstance(payload["counts_by_state"], dict)
    assert isinstance(payload["counts_by_risk_tier"], dict)
    assert isinstance(payload["average_confidence_score"], float)
    assert "items" not in payload


def test_dashboard_endpoint_returns_aggregated_payload(client):
    token = _login(client, "a@example.com", "pass-a")
    campaign = _create_campaign(client, token, name="Dashboard Campaign", domain="dashboard.example")

    response = client.get(
        f"/api/v1/dashboard?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert "technical_score" in payload
    assert "entity_score" in payload
    assert "recommendation_summary" in payload
    assert "latest_crawl_status" in payload
    assert "report_status_summary" in payload
    assert "slo_health_snapshot" in payload
    assert payload["platform_state"] in {"Healthy", "Degraded", "Critical"}


def test_report_schedule_put_get_and_retry_cap(client, db_session, monkeypatch):
    token = _login(client, "a@example.com", "pass-a")
    campaign = _create_campaign(client, token, name="Schedule Campaign", domain="schedule.example")
    headers = {"Authorization": f"Bearer {token}"}
    next_run = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()

    upsert = client.put(
        "/api/v1/reports/schedule",
        json={
            "campaign_id": campaign["id"],
            "cadence": "daily",
            "timezone": "UTC",
            "next_run_at": next_run,
            "enabled": True,
        },
        headers=headers,
    )
    assert upsert.status_code == 200
    assert upsert.json()["data"]["retry_count"] == 0

    fetched = client.get(f"/api/v1/reports/schedule?campaign_id={campaign['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["cadence"] == "daily"

    def _fail(*_args, **_kwargs):
        raise RuntimeError("forced failure")

    monkeypatch.setattr("app.tasks.tasks.reporting_service.run_due_report_schedule", _fail)

    for _ in range(2):
        try:
            tasks.reporting_process_schedule.run(tenant_id=campaign["tenant_id"], campaign_id=campaign["id"])
        except RuntimeError:
            pass
    third = tasks.reporting_process_schedule.run(tenant_id=campaign["tenant_id"], campaign_id=campaign["id"])
    assert third["status"] == "max_retries_exceeded"

    row = (
        db_session.query(ReportSchedule)
        .filter(ReportSchedule.tenant_id == campaign["tenant_id"], ReportSchedule.campaign_id == campaign["id"])
        .first()
    )
    assert row is not None
    assert row.retry_count == 3
    assert row.enabled is False


def test_validation_errors_use_global_exception_envelope(client):
    token = _login(client, "a@example.com", "pass-a")
    response = client.put("/api/v1/reports/schedule", json={}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert len(payload["errors"]) >= 1
