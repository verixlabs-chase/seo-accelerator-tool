from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from time import monotonic, sleep
from typing import Any

from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from app.models.platform_job import PlatformJob

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_DEAD_LETTER = "dead_letter"
JOB_STATUS_CANCELLED = "cancelled"


class ProviderRunDispatchBusy(RuntimeError):
    """A different worker still owns the bounded paid-run dispatch fence."""


class JobClaimOwnershipLost(RuntimeError):
    """A durable job lease was reclaimed by a different worker."""


def create_job(
    db: Session,
    *,
    job_type: str,
    entity_type: str,
    entity_id: str | None,
    payload: dict[str, Any] | None = None,
    tenant_id: str | None = None,
    idempotency_key: str | None = None,
    available_at: datetime | None = None,
    max_retries: int = 3,
) -> PlatformJob:
    if idempotency_key:
        existing = (
            db.query(PlatformJob)
            .filter(PlatformJob.idempotency_key == idempotency_key)
            .first()
        )
        if existing is not None:
            return existing

    row = PlatformJob(
        tenant_id=tenant_id,
        job_type=job_type,
        entity_type=entity_type,
        entity_id=entity_id,
        idempotency_key=idempotency_key,
        status=JOB_STATUS_QUEUED,
        payload=payload or {},
        available_at=available_at or datetime.now(UTC),
        max_retries=max(0, int(max_retries)),
    )
    db.add(row)
    db.flush()
    return row


def claim_jobs(
    db: Session,
    *,
    worker_id: str,
    limit: int,
    lease_seconds: int,
    now: datetime | None = None,
) -> list[PlatformJob]:
    resolved_now = now or datetime.now(UTC)
    claim_limit = max(1, min(int(limit), 25))
    lease_until = resolved_now + timedelta(seconds=max(30, int(lease_seconds)))

    rows = (
        db.query(PlatformJob)
        .filter(
            or_(
                and_(
                    PlatformJob.status == JOB_STATUS_QUEUED,
                    PlatformJob.available_at <= resolved_now,
                ),
                and_(
                    PlatformJob.status == JOB_STATUS_RUNNING,
                    PlatformJob.lease_expires_at.isnot(None),
                    PlatformJob.lease_expires_at <= resolved_now,
                ),
            )
        )
        .order_by(PlatformJob.available_at.asc(), PlatformJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(claim_limit)
        .all()
    )

    for row in rows:
        row.status = JOB_STATUS_RUNNING
        row.started_at = row.started_at or resolved_now
        row.finished_at = None
        row.locked_at = resolved_now
        row.lease_expires_at = lease_until
        row.locked_by = worker_id
        row.error = None
    db.flush()
    return rows


def start_job(
    db: Session,
    job_id: str,
    *,
    worker_id: str | None = None,
    lease_seconds: int = 120,
) -> PlatformJob | None:
    row = db.get(PlatformJob, job_id)
    if row is None:
        return None
    now = datetime.now(UTC)
    row.status = JOB_STATUS_RUNNING
    row.started_at = row.started_at or now
    row.locked_at = now
    row.lease_expires_at = now + timedelta(seconds=max(30, int(lease_seconds)))
    row.locked_by = worker_id
    row.error = None
    db.flush()
    return row


def complete_job(
    db: Session,
    job_id: str,
    result: dict[str, Any] | None = None,
    *,
    expected_worker_id: str | None = None,
) -> PlatformJob | None:
    query = db.query(PlatformJob).filter(PlatformJob.id == job_id).populate_existing()
    if expected_worker_id is not None:
        query = query.filter(
            PlatformJob.status == JOB_STATUS_RUNNING,
            PlatformJob.locked_by == expected_worker_id,
        )
    row = query.with_for_update().one_or_none()
    if row is None:
        return None
    row.status = JOB_STATUS_COMPLETED
    row.result = result or {}
    row.finished_at = datetime.now(UTC)
    row.error = None
    row.locked_at = None
    row.lease_expires_at = None
    row.locked_by = None
    db.flush()
    return row


def release_jobs(
    db: Session,
    *,
    job_ids: list[str],
    worker_id: str,
    now: datetime | None = None,
) -> int:
    if not job_ids:
        return 0
    resolved_now = now or datetime.now(UTC)
    rows = (
        db.query(PlatformJob)
        .filter(
            PlatformJob.id.in_(job_ids),
            PlatformJob.status == JOB_STATUS_RUNNING,
            PlatformJob.locked_by == worker_id,
        )
        .all()
    )
    for row in rows:
        row.status = JOB_STATUS_QUEUED
        row.available_at = resolved_now
        row.locked_at = None
        row.lease_expires_at = None
        row.locked_by = None
    db.flush()
    return len(rows)


def fail_job(db: Session, job_id: str, error: str) -> PlatformJob | None:
    row = db.get(PlatformJob, job_id)
    if row is None:
        return None
    row.status = JOB_STATUS_FAILED
    row.error = error
    row.retry_count = int(row.retry_count or 0) + 1
    row.finished_at = datetime.now(UTC)
    row.locked_at = None
    row.lease_expires_at = None
    row.locked_by = None
    db.flush()
    return row


def record_job_failure(
    db: Session,
    job_id: str,
    *,
    error: str,
    retry_base_seconds: int = 30,
    expected_worker_id: str | None = None,
) -> PlatformJob | None:
    query = db.query(PlatformJob).filter(PlatformJob.id == job_id).populate_existing()
    if expected_worker_id is not None:
        query = query.filter(
            PlatformJob.status == JOB_STATUS_RUNNING,
            PlatformJob.locked_by == expected_worker_id,
        )
    row = query.with_for_update().one_or_none()
    if row is None:
        return None

    now = datetime.now(UTC)
    next_retry_count = int(row.retry_count or 0) + 1
    row.retry_count = next_retry_count
    row.error = error[:4000]
    row.result = None
    row.locked_at = None
    row.lease_expires_at = None
    row.locked_by = None

    if next_retry_count > max(0, int(row.max_retries or 0)):
        row.status = JOB_STATUS_DEAD_LETTER
        row.finished_at = now
    else:
        delay_seconds = min(
            3600,
            max(1, int(retry_base_seconds)) * (2 ** max(0, next_retry_count - 1)),
        )
        row.status = JOB_STATUS_QUEUED
        row.available_at = now + timedelta(seconds=delay_seconds)
        row.finished_at = None
    db.flush()
    return row


def claimed_job_is_current(
    db: Session,
    *,
    job_id: str,
    expected_worker_id: str,
) -> bool:
    """Lock and verify a durable-job ownership token before terminal mutation."""
    row = (
        db.query(PlatformJob.id)
        .filter(
            PlatformJob.id == job_id,
            PlatformJob.status == JOB_STATUS_RUNNING,
            PlatformJob.locked_by == expected_worker_id,
        )
        .with_for_update()
        .one_or_none()
    )
    return row is not None


def lock_claimed_job(
    db: Session,
    *,
    job_id: str,
    expected_worker_id: str,
) -> PlatformJob:
    """Fence one provider call with the current durable-job ownership row."""
    row = (
        db.query(PlatformJob)
        .filter(
            PlatformJob.id == job_id,
            PlatformJob.status == JOB_STATUS_RUNNING,
            PlatformJob.locked_by == expected_worker_id,
        )
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise JobClaimOwnershipLost("This job is now owned by a different worker.")
    return row


@contextmanager
def serialized_provider_run_dispatch(
    db: Session,
    *,
    scope: str,
    wait_seconds: float = 5.0,
) -> Iterator[bool]:
    """Serialize one paid run across commits and expired durable-job leases.

    PostgreSQL session advisory locks live on a dedicated checked-out
    connection, so they survive the service's intentional commits between a
    durable run claim and provider batches. Process/connection death releases
    the fence. Other dialects still use the run-row claim but cannot provide
    the cross-commit crash signal returned by this context manager.
    """
    bind = db.get_bind()
    dialect = bind.dialect.name.lower()
    if dialect != "postgresql":
        yield False
        return

    engine = bind.engine if hasattr(bind, "engine") else bind
    lock_connection = engine.connect()
    acquired = False
    try:
        deadline = monotonic() + max(0.1, float(wait_seconds))
        while monotonic() < deadline:
            acquired = bool(
                lock_connection.execute(
                    text("SELECT pg_try_advisory_lock(hashtextextended(:scope, 0))"),
                    {"scope": scope},
                ).scalar_one()
            )
            if acquired:
                break
            sleep(0.05)
        if not acquired:
            raise ProviderRunDispatchBusy(
                "This paid update is already being handled by another worker."
            )
        yield True
    finally:
        try:
            if acquired:
                lock_connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:scope, 0))"),
                    {"scope": scope},
                )
        finally:
            lock_connection.close()


def durable_job_health(
    db: Session,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return database-backed queue truth suitable for alerts and operations."""
    resolved_now = now or datetime.now(UTC)
    status_rows = (
        db.query(PlatformJob.status, func.count(PlatformJob.id))
        .group_by(PlatformJob.status)
        .order_by(PlatformJob.status.asc())
        .all()
    )
    status_counts: dict[str, int] = {}
    for status_value, count_value in status_rows:
        key = str(status_value or "unknown")
        status_counts[key] = int(count_value or 0)

    stale_lease_count = (
        db.query(PlatformJob)
        .filter(
            PlatformJob.status == JOB_STATUS_RUNNING,
            PlatformJob.lease_expires_at.isnot(None),
            PlatformJob.lease_expires_at <= resolved_now,
        )
        .count()
    )
    retry_backlog_count = (
        db.query(PlatformJob)
        .filter(
            PlatformJob.status == JOB_STATUS_QUEUED,
            PlatformJob.retry_count > 0,
        )
        .count()
    )
    oldest_due = (
        db.query(PlatformJob)
        .filter(
            PlatformJob.status == JOB_STATUS_QUEUED,
            PlatformJob.available_at <= resolved_now,
        )
        .order_by(PlatformJob.available_at.asc(), PlatformJob.created_at.asc())
        .first()
    )
    oldest_due_seconds = 0
    if oldest_due is not None:
        available_at = oldest_due.available_at
        if available_at.tzinfo is None:
            available_at = available_at.replace(tzinfo=UTC)
        oldest_due_seconds = max(0, int((resolved_now - available_at).total_seconds()))

    dead_letter_count = status_counts.get(JOB_STATUS_DEAD_LETTER, 0)
    alerts = {
        "dead_letter_jobs": dead_letter_count > 0,
        "stale_leases": stale_lease_count > 0,
        "retry_backlog": retry_backlog_count > 0,
        "oldest_due_over_five_minutes": oldest_due_seconds > 300,
    }
    return {
        "truth_scope": {
            "mode": "database",
            "durable": True,
            "multi_instance_safe": True,
        },
        "status_counts": status_counts,
        "dead_letter_count": dead_letter_count,
        "stale_lease_count": stale_lease_count,
        "retry_backlog_count": retry_backlog_count,
        "oldest_due_seconds": oldest_due_seconds,
        "alert_state": alerts,
        "healthy": not any(alerts.values()),
        "checked_at": resolved_now.isoformat(),
    }
