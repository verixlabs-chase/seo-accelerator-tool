from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.api.v1 import internal_jobs
from app.services import durable_job_service
from app.models.platform_job import PlatformJob
from app.models.reporting import MonthlyReport, ReportSchedule
from tests.conftest import create_test_campaign


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_internal_job_drain_requires_configured_matching_secret(client, monkeypatch) -> None:
    unconfigured = client.get("/api/v1/internal/jobs/drain")
    assert unconfigured.status_code == 503

    monkeypatch.setattr(
        internal_jobs,
        "get_settings",
        lambda: SimpleNamespace(cron_secret="test-cron-secret"),
    )
    unauthorized = client.get(
        "/api/v1/internal/jobs/drain",
        headers={"Authorization": "Bearer wrong"},
    )
    assert unauthorized.status_code == 401


def test_internal_job_drain_processes_due_report_schedule(
    client,
    db_session,
    monkeypatch,
) -> None:
    token = _login(client, "a@example.com", "pass-a")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Durable Report Schedule", "domain": "durable-report.example"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    saved = client.put(
        "/api/v1/reports/schedule",
        json={
            "campaign_id": campaign["id"],
            "cadence": "daily",
            "timezone": "UTC",
            "next_run_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "enabled": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert saved.status_code == 200

    monkeypatch.setattr(
        internal_jobs,
        "get_settings",
        lambda: SimpleNamespace(cron_secret="test-cron-secret"),
    )
    drained = client.get(
        "/api/v1/internal/jobs/drain",
        headers={
            "Authorization": "Bearer test-cron-secret",
            "x-vercel-id": "test-invocation",
        },
    )
    assert drained.status_code == 200
    payload = drained.json()["data"]
    assert payload["due_report_schedules_seen"] == 1
    assert payload["claimed"] == 1
    assert payload["processed"] == 1
    assert payload["status_counts"] == {"completed": 1}

    job = (
        db_session.query(PlatformJob)
        .filter(
            PlatformJob.job_type == "reporting.process_schedule",
            PlatformJob.entity_id == campaign["id"],
        )
        .one()
    )
    assert job.status == "completed"
    assert job.max_retries == 2
    assert job.locked_by is None

    report_count = (
        db_session.query(MonthlyReport)
        .filter(MonthlyReport.campaign_id == campaign["id"])
        .count()
    )
    assert report_count == 1

    schedule = (
        db_session.query(ReportSchedule)
        .filter(ReportSchedule.campaign_id == campaign["id"])
        .one()
    )
    assert schedule.last_status == "success"
    comparison_now = datetime.now(UTC)
    if schedule.next_run_at.tzinfo is None:
        comparison_now = comparison_now.replace(tzinfo=None)
    assert schedule.next_run_at > comparison_now


def test_internal_job_drain_runs_daily_intelligence_cycle_idempotently(
    client,
    db_session,
    create_test_tenant,
    create_test_org,
    monkeypatch,
) -> None:
    tenant = create_test_tenant(name="Durable Intelligence Tenant")
    organization = create_test_org(
        tenant_id=tenant.id,
        name="Durable Intelligence Org",
    )
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant.id,
        name="Durable Intelligence Campaign",
        domain="durable-intelligence.example",
    )
    campaign.setup_state = "Active"
    db_session.commit()

    calls: list[str] = []

    def _run_campaign_cycle(campaign_id: str, db) -> dict:  # noqa: ANN001
        calls.append(campaign_id)
        return {
            "campaign_id": campaign_id,
            "activation": {
                "mode": "recommendation_only",
                "mutation_scheduling_enabled": False,
                "mutation_execution_enabled": False,
            },
            "recommendations_generated": 1,
            "executions_scheduled": 0,
            "executions_completed": 0,
        }

    monkeypatch.setattr(
        durable_job_service,
        "run_campaign_cycle",
        _run_campaign_cycle,
    )
    monkeypatch.setattr(
        internal_jobs,
        "get_settings",
        lambda: SimpleNamespace(cron_secret="test-cron-secret"),
    )

    first = client.get(
        "/api/v1/internal/jobs/drain",
        headers={"Authorization": "Bearer test-cron-secret"},
    )
    assert first.status_code == 200
    first_payload = first.json()["data"]
    assert first_payload["due_intelligence_campaigns_seen"] == 1
    assert first_payload["processed"] == 1
    assert calls == [campaign.id]

    job = (
        db_session.query(PlatformJob)
        .filter(
            PlatformJob.job_type == "intelligence.campaign_cycle",
            PlatformJob.entity_id == campaign.id,
        )
        .one()
    )
    assert job.status == "completed"
    assert job.result["activation"]["mode"] == "recommendation_only"
    assert job.result["executions_scheduled"] == 0

    second = client.get(
        "/api/v1/internal/jobs/drain",
        headers={"Authorization": "Bearer test-cron-secret"},
    )
    assert second.status_code == 200
    second_payload = second.json()["data"]
    assert second_payload["due_intelligence_campaigns_seen"] == 1
    assert second_payload["claimed"] == 0
    assert second_payload["processed"] == 0
    assert calls == [campaign.id]
