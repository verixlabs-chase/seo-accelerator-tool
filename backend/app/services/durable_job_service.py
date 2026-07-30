from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
import json
from time import monotonic
from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.intelligence.intelligence_orchestrator import run_campaign_cycle
from app.intelligence.lexicon.loader import get_builtin_lexicon
from app.intelligence.lexicon.standards import run_and_record_crux_standards_check
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.platform_job import PlatformJob
from app.models.reporting import ReportSchedule
from app.services import (
    data_connections_service,
    job_service,
    reporting_service,
    traffic_fact_service,
)

JobHandler = Callable[[Session, PlatformJob], dict[str, Any]]

REPORT_SCHEDULE_JOB_TYPE = "reporting.process_schedule"
INTELLIGENCE_CAMPAIGN_CYCLE_JOB_TYPE = "intelligence.campaign_cycle"
SEARCH_CONSOLE_SYNC_JOB_TYPE = "data_connections.search_console_sync"
CWV_STANDARDS_CHECK_JOB_TYPE = "reference_library.cwv_standards_check"


def _json_safe(value: dict[str, Any] | None) -> dict[str, Any]:
    return json.loads(json.dumps(value or {}, default=str))


def _report_schedule_handler(db: Session, job: PlatformJob) -> dict[str, Any]:
    tenant_id = str(job.tenant_id or job.payload.get("tenant_id") or "").strip()
    campaign_id = str(job.payload.get("campaign_id") or job.entity_id or "").strip()
    if not tenant_id or not campaign_id:
        raise ValueError("Report schedule job is missing tenant_id or campaign_id.")
    return reporting_service.run_due_report_schedule(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        commit=False,
    )


def _intelligence_campaign_cycle_handler(
    db: Session,
    job: PlatformJob,
) -> dict[str, Any]:
    tenant_id = str(job.tenant_id or job.payload.get("tenant_id") or "").strip()
    campaign_id = str(job.payload.get("campaign_id") or job.entity_id or "").strip()
    campaign = db.get(Campaign, campaign_id) if campaign_id else None
    if (
        not tenant_id
        or campaign is None
        or campaign.tenant_id != tenant_id
        or campaign.setup_state.lower() != "active"
    ):
        raise ValueError("Intelligence cycle job has no active tenant-scoped campaign.")
    return run_campaign_cycle(campaign_id, db=db)


def _search_console_sync_handler(
    db: Session,
    job: PlatformJob,
) -> dict[str, Any]:
    tenant_id = str(job.tenant_id or job.payload.get("tenant_id") or "").strip()
    connection_id = str(job.payload.get("connection_id") or job.entity_id or "").strip()
    connection = db.get(DataConnection, connection_id) if connection_id else None
    if (
        not tenant_id
        or connection is None
        or connection.tenant_id != tenant_id
        or connection.provider_name != data_connections_service.GOOGLE_SEARCH_CONSOLE_PROVIDER
        or connection.status == data_connections_service.CONNECTION_STATUS_DISCONNECTED
    ):
        raise ValueError("Search Console sync job has no active tenant-scoped connection.")
    campaign = db.get(Campaign, connection.campaign_id)
    if (
        campaign is None
        or campaign.tenant_id != tenant_id
        or campaign.organization_id != connection.organization_id
        or campaign.business_location_id != connection.business_location_id
    ):
        raise ValueError("Search Console connection mapping is no longer valid.")

    start_date, end_date = _search_console_sync_window(connection, payload=job.payload)
    data_connections_service.mark_sync_started(db, connection)
    result = traffic_fact_service.sync_search_console_daily_metrics_for_campaign(
        db=db,
        campaign=campaign,
        start_date=start_date,
        end_date=end_date,
        site_url=connection.external_resource_id,
    )
    data_connections_service.mark_sync_succeeded(
        db,
        connection,
        metric_start_date=start_date.isoformat(),
        metric_end_date=end_date.isoformat(),
    )
    return {
        "connection_id": connection.id,
        "campaign_id": campaign.id,
        "business_location_id": connection.business_location_id,
        "provider_name": connection.provider_name,
        "external_resource_id": connection.external_resource_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "requested_days": result.requested_days,
        "provider_calls": result.provider_calls,
        "inserted_rows": result.inserted_rows,
        "updated_rows": result.updated_rows,
        "skipped_rows": result.skipped_rows,
        "status": result.status,
    }


def _cwv_standards_check_handler(
    db: Session,
    job: PlatformJob,
) -> dict[str, Any]:
    settings = get_settings()
    origin = str(job.payload.get("origin") or settings.cwv_standards_probe_origin).strip()
    return run_and_record_crux_standards_check(
        db,
        lexicon=get_builtin_lexicon(),
        api_key=settings.crux_api_key,
        origin=origin,
        timeout_seconds=settings.google_oauth_http_timeout_seconds,
    )


DEFAULT_HANDLERS: dict[str, JobHandler] = {
    REPORT_SCHEDULE_JOB_TYPE: _report_schedule_handler,
    INTELLIGENCE_CAMPAIGN_CYCLE_JOB_TYPE: _intelligence_campaign_cycle_handler,
    SEARCH_CONSOLE_SYNC_JOB_TYPE: _search_console_sync_handler,
    CWV_STANDARDS_CHECK_JOB_TYPE: _cwv_standards_check_handler,
}


def _search_console_sync_window(
    connection: DataConnection,
    *,
    payload: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> tuple[date, date]:
    resolved_now = now or datetime.now(UTC)
    settings = get_settings()
    end_date = resolved_now.date() - timedelta(
        days=max(0, int(settings.data_connection_sync_delay_days))
    )
    payload = payload or {}
    payload_start = str(payload.get("start_date") or "").strip()
    payload_end = str(payload.get("end_date") or "").strip()
    if payload_start and payload_end:
        return date.fromisoformat(payload_start), date.fromisoformat(payload_end)

    sync_cursor = dict(connection.sync_cursor or {})
    cursor_date_raw = str(sync_cursor.get("last_metric_date") or "").strip()
    target_backfill_days = max(
        1,
        min(
            int(settings.data_connection_initial_backfill_days),
            data_connections_service.MAX_SEARCH_CONSOLE_RANGE_DAYS,
        ),
    )
    if cursor_date_raw:
        cursor_date = date.fromisoformat(cursor_date_raw)
        history_start_raw = str(sync_cursor.get("history_start_date") or "").strip()
        history_start = date.fromisoformat(history_start_raw) if history_start_raw else None
        stored_history_days = (
            (cursor_date - history_start).days + 1
            if history_start is not None and history_start <= cursor_date
            else 0
        )
        if stored_history_days < target_backfill_days:
            backfill_end = min(cursor_date, end_date)
            return (
                backfill_end - timedelta(days=target_backfill_days - 1),
                backfill_end,
            )
        start_date = min(cursor_date + timedelta(days=1), end_date)
    else:
        start_date = end_date - timedelta(days=target_backfill_days - 1)
    return start_date, end_date


def _search_console_sync_idempotency_key(
    connection_id: str,
    *,
    start_date: date,
    end_date: date,
) -> str:
    del start_date
    # v2 intentionally separates the 16-month history rollout from older
    # 28-day jobs while keeping repeat requests for the same reporting day
    # idempotent after the initial backfill completes.
    return f"search-console-sync:{connection_id}:v2:{end_date.isoformat()}"


def create_search_console_sync_job(
    db: Session,
    *,
    connection: DataConnection,
    now: datetime | None = None,
) -> PlatformJob:
    resolved_now = now or datetime.now(UTC)
    start_date, end_date = _search_console_sync_window(connection, now=resolved_now)
    return job_service.create_job(
        db,
        tenant_id=connection.tenant_id,
        job_type=SEARCH_CONSOLE_SYNC_JOB_TYPE,
        entity_type="data_connection",
        entity_id=connection.id,
        idempotency_key=_search_console_sync_idempotency_key(
            connection.id,
            start_date=start_date,
            end_date=end_date,
        ),
        payload={
            "tenant_id": connection.tenant_id,
            "organization_id": connection.organization_id,
            "connection_id": connection.id,
            "campaign_id": connection.campaign_id,
            "business_location_id": connection.business_location_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        available_at=resolved_now,
        max_retries=2,
    )


def enqueue_due_data_connection_jobs(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 25,
) -> int:
    resolved_now = now or datetime.now(UTC)
    rows = (
        db.query(DataConnection)
        .filter(
            DataConnection.provider_name == data_connections_service.GOOGLE_SEARCH_CONSOLE_PROVIDER,
            DataConnection.status != data_connections_service.CONNECTION_STATUS_DISCONNECTED,
            DataConnection.next_sync_at.isnot(None),
            DataConnection.next_sync_at <= resolved_now,
        )
        .order_by(DataConnection.next_sync_at.asc(), DataConnection.id.asc())
        .with_for_update(skip_locked=True)
        .limit(max(1, min(int(limit), 100)))
        .all()
    )
    for connection in rows:
        create_search_console_sync_job(db, connection=connection, now=resolved_now)
    db.flush()
    return len(rows)


def run_search_console_sync_now(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    connection_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_now = now or datetime.now(UTC)
    connection = (
        db.query(DataConnection)
        .filter(
            DataConnection.id == connection_id,
            DataConnection.tenant_id == tenant_id,
            DataConnection.organization_id == organization_id,
            DataConnection.provider_name == data_connections_service.GOOGLE_SEARCH_CONSOLE_PROVIDER,
            DataConnection.status != data_connections_service.CONNECTION_STATUS_DISCONNECTED,
        )
        .first()
    )
    if connection is None:
        raise ValueError("Search Console connection not found.")

    start_date, end_date = _search_console_sync_window(connection, now=resolved_now)
    idempotency_key = _search_console_sync_idempotency_key(
        connection.id,
        start_date=start_date,
        end_date=end_date,
    )
    existing = db.query(PlatformJob).filter(PlatformJob.idempotency_key == idempotency_key).first()
    job = create_search_console_sync_job(db, connection=connection, now=resolved_now)
    created = existing is None
    db.commit()
    db.refresh(job)
    if job.status == job_service.JOB_STATUS_COMPLETED:
        return {
            "job_id": job.id,
            "status": job.status,
            "created": False,
            "idempotent_replay": True,
            "result": _json_safe(job.result),
            "error": job.error,
        }
    if job.status in {job_service.JOB_STATUS_RUNNING, job_service.JOB_STATUS_DEAD_LETTER}:
        return {
            "job_id": job.id,
            "status": job.status,
            "created": False,
            "idempotent_replay": False,
            "result": _json_safe(job.result),
            "error": job.error,
        }

    job_service.start_job(
        db,
        job.id,
        worker_id=f"tenant-data-connection-{uuid.uuid4()}",
        lease_seconds=get_settings().durable_job_lease_seconds,
    )
    db.commit()
    execution = execute_claimed_job(db, job_id=job.id)
    refreshed = db.get(PlatformJob, job.id)
    return {
        "job_id": job.id,
        "status": execution["status"],
        "created": created,
        "idempotent_replay": False,
        "result": _json_safe(refreshed.result if refreshed is not None else None),
        "error": refreshed.error if refreshed is not None else None,
    }


def enqueue_due_report_schedule_jobs(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 25,
) -> int:
    resolved_now = now or datetime.now(UTC)
    rows = (
        db.query(ReportSchedule)
        .filter(
            ReportSchedule.enabled.is_(True),
            ReportSchedule.next_run_at <= resolved_now,
            ReportSchedule.last_status != "max_retries_exceeded",
        )
        .order_by(ReportSchedule.next_run_at.asc(), ReportSchedule.id.asc())
        .with_for_update(skip_locked=True)
        .limit(max(1, min(int(limit), 100)))
        .all()
    )

    for row in rows:
        scheduled_for = row.next_run_at
        if scheduled_for.tzinfo is None:
            scheduled_for = scheduled_for.replace(tzinfo=UTC)
        job_service.create_job(
            db,
            tenant_id=row.tenant_id,
            job_type=REPORT_SCHEDULE_JOB_TYPE,
            entity_type="campaign",
            entity_id=row.campaign_id,
            idempotency_key=f"report-schedule:{row.id}:{scheduled_for.isoformat()}",
            payload={
                "tenant_id": row.tenant_id,
                "campaign_id": row.campaign_id,
                "report_schedule_id": row.id,
                "scheduled_for": scheduled_for.isoformat(),
            },
            available_at=resolved_now,
            max_retries=max(0, reporting_service.REPORT_SCHEDULE_MAX_RETRIES - 1),
        )
    db.flush()
    return len(rows)


def enqueue_due_intelligence_campaign_jobs(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 25,
) -> int:
    resolved_now = now or datetime.now(UTC)
    cycle_date = resolved_now.date().isoformat()
    rows = (
        db.query(Campaign)
        .filter(Campaign.setup_state.in_(["Active", "active"]))
        .order_by(Campaign.created_at.asc(), Campaign.id.asc())
        .limit(max(1, min(int(limit), 100)))
        .all()
    )
    for campaign in rows:
        create_intelligence_campaign_job(
            db,
            campaign=campaign,
            cycle_date=cycle_date,
            available_at=resolved_now,
        )
    db.flush()
    return len(rows)


def create_intelligence_campaign_job(
    db: Session,
    *,
    campaign: Campaign,
    cycle_date: str,
    available_at: datetime | None = None,
) -> PlatformJob:
    return job_service.create_job(
        db,
        tenant_id=campaign.tenant_id,
        job_type=INTELLIGENCE_CAMPAIGN_CYCLE_JOB_TYPE,
        entity_type="campaign",
        entity_id=campaign.id,
        idempotency_key=f"intelligence-cycle:{campaign.id}:{cycle_date}",
        payload={
            "tenant_id": campaign.tenant_id,
            "campaign_id": campaign.id,
            "cycle_date": cycle_date,
            "provider_checks_allowed": False,
        },
        available_at=available_at or datetime.now(UTC),
        max_retries=2,
    )


def enqueue_due_cwv_standards_check(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    settings = get_settings()
    if not settings.intelligence_lexicon_enabled or not settings.crux_api_key.strip():
        return 0
    resolved_now = now or datetime.now(UTC)
    interval_days = max(1, int(settings.cwv_standards_review_interval_days))
    interval_bucket = resolved_now.date().toordinal() // interval_days
    job_service.create_job(
        db,
        tenant_id=None,
        job_type=CWV_STANDARDS_CHECK_JOB_TYPE,
        entity_type="reference_standard",
        entity_id=None,
        idempotency_key=f"cwv-standards-check:{interval_days}:{interval_bucket}",
        payload={
            "origin": settings.cwv_standards_probe_origin,
            "automatic_activation_allowed": False,
        },
        available_at=resolved_now,
        max_retries=2,
    )
    db.flush()
    return 1


def run_intelligence_campaign_job_now(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_now = now or datetime.now(UTC)
    campaign = db.get(Campaign, campaign_id)
    if (
        campaign is None
        or campaign.tenant_id != tenant_id
        or campaign.setup_state.lower() != "active"
    ):
        raise ValueError("Campaign must be active and tenant-scoped.")

    cycle_date = resolved_now.date().isoformat()
    idempotency_key = f"intelligence-cycle:{campaign.id}:{cycle_date}"
    existing = db.query(PlatformJob).filter(PlatformJob.idempotency_key == idempotency_key).first()
    job = create_intelligence_campaign_job(
        db,
        campaign=campaign,
        cycle_date=cycle_date,
        available_at=resolved_now,
    )
    created = existing is None
    db.commit()
    db.refresh(job)

    if job.status == job_service.JOB_STATUS_COMPLETED:
        return {
            "job_id": job.id,
            "status": job.status,
            "created": created,
            "idempotent_replay": True,
            "result": _json_safe(job.result),
            "error": job.error,
        }
    lease_expires_at = job.lease_expires_at
    if lease_expires_at is not None and lease_expires_at.tzinfo is None:
        lease_expires_at = lease_expires_at.replace(tzinfo=UTC)
    if job.status == job_service.JOB_STATUS_RUNNING and (
        lease_expires_at is None or lease_expires_at > resolved_now
    ):
        return {
            "job_id": job.id,
            "status": job.status,
            "created": created,
            "idempotent_replay": False,
            "result": _json_safe(job.result),
            "error": job.error,
        }
    if job.status == job_service.JOB_STATUS_DEAD_LETTER:
        return {
            "job_id": job.id,
            "status": job.status,
            "created": created,
            "idempotent_replay": False,
            "result": _json_safe(job.result),
            "error": job.error,
        }

    job_service.start_job(
        db,
        job.id,
        worker_id=f"tenant-intelligence-{uuid.uuid4()}",
        lease_seconds=get_settings().durable_job_lease_seconds,
    )
    db.commit()
    execution = execute_claimed_job(db, job_id=job.id)
    refreshed = db.get(PlatformJob, job.id)
    return {
        "job_id": job.id,
        "status": execution["status"],
        "created": created,
        "idempotent_replay": False,
        "result": _json_safe(refreshed.result if refreshed is not None else None),
        "error": refreshed.error if refreshed is not None else None,
    }


def _record_handler_failure(
    db: Session,
    *,
    job_type: str,
    payload: dict[str, Any],
    tenant_id: str | None,
    error: Exception,
) -> None:
    if job_type == SEARCH_CONSOLE_SYNC_JOB_TYPE:
        connection_id = str(payload.get("connection_id") or "").strip()
        if connection_id:
            data_connections_service.mark_sync_failed(
                db,
                connection_id=connection_id,
                error=error,
            )
        return
    if job_type != REPORT_SCHEDULE_JOB_TYPE:
        return
    campaign_id = str(payload.get("campaign_id") or "").strip()
    resolved_tenant_id = str(tenant_id or payload.get("tenant_id") or "").strip()
    if not campaign_id or not resolved_tenant_id:
        return
    reporting_service.mark_schedule_attempt_failure(
        db,
        tenant_id=resolved_tenant_id,
        campaign_id=campaign_id,
        error_message=str(error),
        commit=False,
    )


def execute_claimed_job(
    db: Session,
    *,
    job_id: str,
    handlers: dict[str, JobHandler] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    handler_map = handlers or DEFAULT_HANDLERS
    job = db.get(PlatformJob, job_id)
    if job is None:
        return {"job_id": job_id, "status": "missing"}
    if job.status != job_service.JOB_STATUS_RUNNING:
        return {"job_id": job_id, "status": "not_running"}

    handler = handler_map.get(job.job_type)
    if handler is None:
        job_service.fail_job(db, job.id, f"Unsupported durable job type: {job.job_type}")
        db.commit()
        return {"job_id": job.id, "status": job_service.JOB_STATUS_FAILED}

    job_type = job.job_type
    tenant_id = job.tenant_id
    payload = dict(job.payload or {})
    try:
        result = _json_safe(handler(db, job))
        job_service.complete_job(db, job.id, result=result)
        db.commit()
        return {"job_id": job.id, "status": job_service.JOB_STATUS_COMPLETED}
    except Exception as exc:
        db.rollback()
        try:
            _record_handler_failure(
                db,
                job_type=job_type,
                payload=payload,
                tenant_id=tenant_id,
                error=exc,
            )
        except Exception:
            db.rollback()

        failed = job_service.record_job_failure(
            db,
            job_id,
            error=str(exc),
            retry_base_seconds=settings.durable_job_retry_base_seconds,
        )
        db.commit()
        return {
            "job_id": job_id,
            "status": failed.status if failed is not None else "missing",
        }


def drain_platform_jobs(
    db: Session,
    *,
    worker_id: str | None = None,
    batch_size: int | None = None,
    time_budget_seconds: int = 45,
) -> dict[str, Any]:
    settings = get_settings()
    resolved_worker_id = worker_id or f"vercel-cron-{uuid.uuid4()}"
    resolved_batch_size = max(
        1,
        min(int(batch_size or settings.durable_job_batch_size), 25),
    )
    started = monotonic()

    due_schedules_seen = enqueue_due_report_schedule_jobs(
        db,
        limit=resolved_batch_size * 5,
    )
    due_intelligence_campaigns_seen = enqueue_due_intelligence_campaign_jobs(
        db,
        limit=resolved_batch_size * 5,
    )
    due_data_connections_seen = enqueue_due_data_connection_jobs(
        db,
        limit=resolved_batch_size * 5,
    )
    due_cwv_standards_checks_seen = enqueue_due_cwv_standards_check(db)
    db.commit()

    claimed = job_service.claim_jobs(
        db,
        worker_id=resolved_worker_id,
        limit=resolved_batch_size,
        lease_seconds=settings.durable_job_lease_seconds,
    )
    claimed_ids = [row.id for row in claimed]
    db.commit()

    results: list[dict[str, Any]] = []
    for job_id in claimed_ids:
        if monotonic() - started >= max(5, int(time_budget_seconds)):
            break
        results.append(execute_claimed_job(db, job_id=job_id))

    processed_ids = {str(result.get("job_id")) for result in results}
    deferred_ids = [job_id for job_id in claimed_ids if job_id not in processed_ids]
    released = job_service.release_jobs(
        db,
        job_ids=deferred_ids,
        worker_id=resolved_worker_id,
    )
    db.commit()

    status_counts: dict[str, int] = {}
    for result in results:
        status_value = str(result.get("status") or "unknown")
        status_counts[status_value] = status_counts.get(status_value, 0) + 1

    return {
        "worker_id": resolved_worker_id,
        "due_report_schedules_seen": due_schedules_seen,
        "due_intelligence_campaigns_seen": due_intelligence_campaigns_seen,
        "due_data_connections_seen": due_data_connections_seen,
        "due_cwv_standards_checks_seen": due_cwv_standards_checks_seen,
        "claimed": len(claimed_ids),
        "processed": len(results),
        "deferred": len(deferred_ids),
        "released": released,
        "status_counts": status_counts,
    }
