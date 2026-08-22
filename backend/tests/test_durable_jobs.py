from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import uuid

from app.api.v1 import internal_jobs
from app.models.campaign import Campaign
from app.models.platform_job import PlatformJob
from app.models.reporting import MonthlyReport, ReportSchedule
from app.services import durable_job_service
from app.services import job_service
from app.services.rate_limit_store import RateLimitStoreUnavailable
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


def test_internal_job_drain_runs_one_bounded_postgres_limiter_cleanup(
    client,
    monkeypatch,
) -> None:
    cleanup_calls: list[dict[str, int]] = []
    store_init_calls: list[dict[str, int]] = []
    drain_calls: list[dict[str, object]] = []

    class _Store:
        def prune_expired(self, *, retention_seconds: int, batch_size: int) -> int:
            cleanup_calls.append(
                {
                    "retention_seconds": retention_seconds,
                    "batch_size": batch_size,
                }
            )
            return 12

    def _store_factory(**kwargs: int) -> _Store:
        store_init_calls.append(kwargs)
        return _Store()

    def _drain(*_args, **kwargs) -> dict[str, int]:  # noqa: ANN003
        drain_calls.append(kwargs)
        return {"claimed": 0, "processed": 0}

    monkeypatch.setattr(
        internal_jobs,
        "get_settings",
        lambda: SimpleNamespace(
            cron_secret="test-cron-secret",
            rate_limit_enabled=True,
            rate_limit_backend="postgres",
        ),
    )
    monkeypatch.setattr(
        internal_jobs.durable_job_service,
        "drain_platform_jobs",
        _drain,
    )
    monkeypatch.setattr(
        internal_jobs,
        "PostgresFixedWindowRateLimitStore",
        _store_factory,
    )

    response = client.get(
        "/api/v1/internal/jobs/drain",
        headers={"Authorization": "Bearer test-cron-secret"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["rate_limit_cleanup"] == {
        "attempted": True,
        "deleted": 12,
        "batches": 1,
        "status": "completed",
    }
    assert cleanup_calls == [
        {"retention_seconds": 172_800, "batch_size": 1_000}
    ]
    assert store_init_calls == [
        {"statement_timeout_ms": 2_000, "lock_timeout_ms": 500}
    ]
    assert len(drain_calls) == 1
    assert drain_calls[0]["time_budget_seconds"] == 40


def test_internal_job_drain_caps_limiter_cleanup_at_one_full_batch(
    client,
    monkeypatch,
) -> None:
    cleanup_calls: list[dict[str, int]] = []
    store_init_calls: list[dict[str, int]] = []

    class _Store:
        def prune_expired(self, *, retention_seconds: int, batch_size: int) -> int:
            cleanup_calls.append(
                {
                    "retention_seconds": retention_seconds,
                    "batch_size": batch_size,
                }
            )
            return batch_size

    def _store_factory(**kwargs: int) -> _Store:
        store_init_calls.append(kwargs)
        return _Store()

    monkeypatch.setattr(
        internal_jobs,
        "get_settings",
        lambda: SimpleNamespace(
            cron_secret="test-cron-secret",
            rate_limit_enabled=True,
            rate_limit_backend="postgres",
        ),
    )
    monkeypatch.setattr(
        internal_jobs.durable_job_service,
        "drain_platform_jobs",
        lambda *_args, **_kwargs: {"claimed": 0, "processed": 0},
    )
    monkeypatch.setattr(
        internal_jobs,
        "PostgresFixedWindowRateLimitStore",
        _store_factory,
    )

    response = client.get(
        "/api/v1/internal/jobs/drain",
        headers={"Authorization": "Bearer test-cron-secret"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["rate_limit_cleanup"] == {
        "attempted": True,
        "deleted": 1_000,
        "batches": 1,
        "status": "batch_limit_reached",
    }
    assert cleanup_calls == [
        {"retention_seconds": 172_800, "batch_size": 1_000}
    ]
    assert store_init_calls == [
        {"statement_timeout_ms": 2_000, "lock_timeout_ms": 500}
    ]


def test_internal_job_drain_reports_limiter_cleanup_unavailable_without_failing(
    client,
    monkeypatch,
) -> None:
    drain_calls: list[dict[str, object]] = []
    store_init_calls: list[dict[str, int]] = []

    class _Store:
        def prune_expired(self, *, retention_seconds: int, batch_size: int) -> int:
            del retention_seconds, batch_size
            raise RateLimitStoreUnavailable("cleanup unavailable")

    def _drain(*_args, **kwargs) -> dict[str, int]:  # noqa: ANN003
        drain_calls.append(kwargs)
        return {"claimed": 3, "processed": 3}

    def _store_factory(**kwargs: int) -> _Store:
        store_init_calls.append(kwargs)
        return _Store()

    monkeypatch.setattr(
        internal_jobs,
        "get_settings",
        lambda: SimpleNamespace(
            cron_secret="test-cron-secret",
            rate_limit_enabled=True,
            rate_limit_backend="postgres",
        ),
    )
    monkeypatch.setattr(
        internal_jobs.durable_job_service,
        "drain_platform_jobs",
        _drain,
    )
    monkeypatch.setattr(
        internal_jobs,
        "PostgresFixedWindowRateLimitStore",
        _store_factory,
    )

    response = client.get(
        "/api/v1/internal/jobs/drain",
        headers={"Authorization": "Bearer test-cron-secret"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["claimed"] == 3
    assert response.json()["data"]["processed"] == 3
    assert response.json()["data"]["rate_limit_cleanup"] == {
        "attempted": True,
        "deleted": 0,
        "batches": 0,
        "status": "unavailable",
    }
    assert len(drain_calls) == 1
    assert drain_calls[0]["time_budget_seconds"] == 40
    assert store_init_calls == [
        {"statement_timeout_ms": 2_000, "lock_timeout_ms": 500}
    ]


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


def test_durable_job_health_uses_database_truth(db_session) -> None:
    now = datetime.now(UTC)
    db_session.add_all(
        [
            PlatformJob(
                id=str(uuid.uuid4()),
                tenant_id=None,
                job_type="test.dead",
                entity_type="test",
                status=job_service.JOB_STATUS_DEAD_LETTER,
                payload={},
                available_at=now - timedelta(minutes=20),
                max_retries=0,
                retry_count=1,
                finished_at=now - timedelta(minutes=10),
            ),
            PlatformJob(
                id=str(uuid.uuid4()),
                tenant_id=None,
                job_type="test.stale",
                entity_type="test",
                status=job_service.JOB_STATUS_RUNNING,
                payload={},
                available_at=now - timedelta(minutes=15),
                max_retries=2,
                retry_count=0,
                lease_expires_at=now - timedelta(minutes=1),
                locked_by="missing-worker",
            ),
            PlatformJob(
                id=str(uuid.uuid4()),
                tenant_id=None,
                job_type="test.retry",
                entity_type="test",
                status=job_service.JOB_STATUS_QUEUED,
                payload={},
                available_at=now - timedelta(minutes=10),
                max_retries=2,
                retry_count=1,
            ),
        ]
    )
    db_session.commit()

    health = job_service.durable_job_health(db_session, now=now)

    assert health["truth_scope"]["mode"] == "database"
    assert health["dead_letter_count"] == 1
    assert health["stale_lease_count"] == 1
    assert health["retry_backlog_count"] == 1
    assert health["oldest_due_seconds"] >= 600
    assert health["healthy"] is False
    assert all(health["alert_state"].values())


def test_stale_worker_cannot_complete_a_newer_job_claim(db_session) -> None:
    job = PlatformJob(
        tenant_id=None,
        job_type="test.claim-cas",
        entity_type="test",
        status=job_service.JOB_STATUS_RUNNING,
        payload={},
        available_at=datetime.now(UTC),
        locked_by="first-worker",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=2),
    )
    db_session.add(job)
    db_session.commit()

    def replace_owner(db, _job):  # noqa: ANN001
        current = db.get(PlatformJob, job.id)
        current.locked_by = "replacement-worker"
        db.commit()
        return {"unsafe": "stale result"}

    outcome = durable_job_service.execute_claimed_job(
        db_session,
        job_id=job.id,
        handlers={"test.claim-cas": replace_owner},
    )

    assert outcome == {"job_id": job.id, "status": "claim_lost"}
    db_session.expire_all()
    current = db_session.get(PlatformJob, job.id)
    assert current.status == job_service.JOB_STATUS_RUNNING
    assert current.locked_by == "replacement-worker"
    assert current.result is None


def test_tenant_cycle_is_idempotent_and_recovers_expired_lease(
    client,
    db_session,
    monkeypatch,
) -> None:
    token_a = _login(client, "a@example.com", "pass-a")
    token_b = _login(client, "b@example.com", "pass-b")
    campaign_payload = client.post(
        "/api/v1/campaigns",
        json={"name": "Manual Intelligence Cycle", "domain": "manual-cycle.example"},
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()["data"]
    campaign = db_session.get(Campaign, campaign_payload["id"])
    assert campaign is not None
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
            "recommendations_generated": 3,
            "executions_scheduled": 0,
            "executions_completed": 0,
        }

    monkeypatch.setattr(
        durable_job_service,
        "run_campaign_cycle",
        _run_campaign_cycle,
    )
    endpoint = (
        "/api/v1/intelligence/cycles/run"
        f"?campaign_id={campaign.id}"
    )
    first = client.post(
        endpoint,
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert first.status_code == 200
    first_payload = first.json()["data"]
    assert first_payload["status"] == "completed"
    assert first_payload["created"] is True
    assert first_payload["idempotent_replay"] is False
    assert first_payload["safety"] == {
        "provider_checks_allowed": False,
        "activation_mode": "recommendation_only",
        "mutation_scheduling_enabled": False,
        "mutation_execution_enabled": False,
        "executions_scheduled": 0,
        "executions_completed": 0,
    }

    job = (
        db_session.query(PlatformJob)
        .filter(
            PlatformJob.job_type == "intelligence.campaign_cycle",
            PlatformJob.entity_id == campaign.id,
        )
        .one()
    )
    job.status = "running"
    job.result = None
    job.finished_at = None
    job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    job.locked_by = "expired-worker"
    db_session.commit()

    recovered = client.post(
        endpoint,
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert recovered.status_code == 200
    recovered_payload = recovered.json()["data"]
    assert recovered_payload["status"] == "completed"
    assert recovered_payload["created"] is False
    assert recovered_payload["idempotent_replay"] is False
    assert calls == [campaign.id, campaign.id]

    replay = client.post(
        endpoint,
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["idempotent_replay"] is True
    assert (
        db_session.query(PlatformJob)
        .filter(
            PlatformJob.job_type == "intelligence.campaign_cycle",
            PlatformJob.entity_id == campaign.id,
        )
        .count()
        == 1
    )

    cross_tenant = client.post(
        endpoint,
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross_tenant.status_code == 404
