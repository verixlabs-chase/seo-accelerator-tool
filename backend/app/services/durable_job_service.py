from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import json
from time import monotonic
from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.platform_job import PlatformJob
from app.models.reporting import ReportSchedule
from app.services import job_service, reporting_service

JobHandler = Callable[[Session, PlatformJob], dict[str, Any]]

REPORT_SCHEDULE_JOB_TYPE = "reporting.process_schedule"


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


DEFAULT_HANDLERS: dict[str, JobHandler] = {
    REPORT_SCHEDULE_JOB_TYPE: _report_schedule_handler,
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


def _record_handler_failure(
    db: Session,
    *,
    job_type: str,
    payload: dict[str, Any],
    tenant_id: str | None,
    error: Exception,
) -> None:
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
        "claimed": len(claimed_ids),
        "processed": len(results),
        "deferred": len(deferred_ids),
        "released": released,
        "status_counts": status_counts,
    }
