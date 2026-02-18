import json
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.models.reporting import ReportSchedule
from app.models.task_execution import TaskExecution
from app.services import entity_service, observability_service
from app.tasks import tasks


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _create_campaign(client, token, name="Hardening Campaign", domain="hardening.example") -> dict:
    response = client.post(
        "/api/v1/campaigns",
        json={"name": name, "domain": domain},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()["data"]


def _latest_task(db_session, tenant_id: str, task_name: str) -> dict:
    row = (
        db_session.query(TaskExecution)
        .filter(TaskExecution.tenant_id == tenant_id, TaskExecution.task_name == task_name)
        .order_by(TaskExecution.created_at.desc())
        .first()
    )
    assert row is not None
    return json.loads(row.result_json or "{}")


def test_failure_simulation_reason_codes_and_retry_cap(client, db_session, monkeypatch):
    token = _login(client, "a@example.com", "pass-a")
    campaign = _create_campaign(client, token, name="Failure Simulation", domain="failure-sim.example")
    tenant_id = campaign["tenant_id"]

    # Proxy failure simulation: rank task fails with connection error.
    monkeypatch.setattr(
        "app.tasks.tasks.rank_service.run_snapshot_collection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionError("proxy failure")),
    )
    with pytest.raises(ConnectionError):
        tasks.rank_schedule_window.run(campaign_id=campaign["id"], tenant_id=tenant_id, location_code="US")
    rank_payload = _latest_task(db_session, tenant_id, "rank.schedule_window")
    assert rank_payload["reason_code"] == "connection_error"

    # Crawl timeout simulation.
    monkeypatch.setattr(
        "app.tasks.tasks.crawl_service.execute_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("crawl timeout")),
    )
    crawl = client.post(
        "/api/v1/crawl/schedule",
        json={"campaign_id": campaign["id"], "crawl_type": "deep", "seed_url": "https://example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    crawl_run_id = crawl.json()["data"]["id"]
    with pytest.raises(TimeoutError):
        tasks.crawl_fetch_batch.run(crawl_run_id=crawl_run_id)
    crawl_payload = _latest_task(db_session, tenant_id, "crawl.fetch_batch")
    assert crawl_payload["reason_code"] == "timeout"

    # Email failure simulation.
    generated = client.post(
        "/api/v1/reports/generate",
        json={"campaign_id": campaign["id"], "month_number": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    report_id = generated.json()["data"]["id"]
    monkeypatch.setattr(
        "app.tasks.tasks.reporting_service.deliver_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("smtp timeout")),
    )
    with pytest.raises(TimeoutError):
        tasks.reporting_send_email.run(tenant_id=tenant_id, report_id=report_id, recipient="ops@example.com")
    email_payload = _latest_task(db_session, tenant_id, "reporting.send_email")
    assert email_payload["reason_code"] == "timeout"

    # Entity analysis failure.
    original_entity_run = entity_service.run_entity_analysis
    monkeypatch.setattr(
        "app.tasks.tasks.entity_service.run_entity_analysis",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionError("entity provider unreachable")),
    )
    with pytest.raises(ConnectionError):
        tasks.entity_analyze_campaign.run(tenant_id=tenant_id, campaign_id=campaign["id"])
    entity_payload = _latest_task(db_session, tenant_id, "entity.analyze_campaign")
    assert entity_payload["reason_code"] == "connection_error"
    monkeypatch.setattr("app.tasks.tasks.entity_service.run_entity_analysis", original_entity_run)

    # Worker crash simulation + retry cap enforcement for schedule processor.
    upsert = client.put(
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
    assert upsert.status_code == 200
    monkeypatch.setattr(
        "app.tasks.tasks.reporting_service.run_due_report_schedule",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("worker crash")),
    )
    for _ in range(2):
        with pytest.raises(RuntimeError):
            tasks.reporting_process_schedule.run(tenant_id=tenant_id, campaign_id=campaign["id"])
    terminal = tasks.reporting_process_schedule.run(tenant_id=tenant_id, campaign_id=campaign["id"])
    assert terminal["status"] == "max_retries_exceeded"

    row = (
        db_session.query(ReportSchedule)
        .filter(ReportSchedule.tenant_id == tenant_id, ReportSchedule.campaign_id == campaign["id"])
        .first()
    )
    assert row is not None
    assert row.enabled is False

    dashboard = client.get(f"/api/v1/dashboard?campaign_id={campaign['id']}", headers={"Authorization": f"Bearer {token}"})
    assert dashboard.status_code == 200
    assert dashboard.json()["data"]["report_status_summary"]["schedule"]["has_failure"] is True
    assert dashboard.json()["data"]["platform_state"] in {"Degraded", "Critical"}


def test_queue_stress_backlog_and_alert_trigger(client):
    # Simulate backlog growth and lag using aged queued timestamps.
    for _ in range(30):
        observability_service.record_task_started({"queued_at": time.time() - (9 * 60)})
    for _ in range(10):
        observability_service.record_task_finished(success=True)

    response = client.get("/api/v1/health/metrics")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["metrics"]["queue_backlog_tasks"] >= 20
    assert payload["alert_state"]["queue_lag"] is True

    # Drain remaining backlog and verify no negative/starvation artifact.
    for _ in range(20):
        observability_service.record_task_finished(success=True)
    response2 = client.get("/api/v1/health/metrics")
    assert response2.status_code == 200
    assert response2.json()["data"]["metrics"]["queue_backlog_tasks"] >= 0
