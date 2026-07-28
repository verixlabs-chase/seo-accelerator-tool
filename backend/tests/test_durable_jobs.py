from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.api.v1 import internal_jobs
from app.models.platform_job import PlatformJob
from app.models.reporting import MonthlyReport, ReportSchedule


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
