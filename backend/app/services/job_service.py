from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.platform_job import PlatformJob


def create_job(
    db: Session,
    *,
    job_type: str,
    entity_type: str,
    entity_id: str | None,
    payload: dict[str, Any] | None = None,
) -> PlatformJob:
    row = PlatformJob(
        job_type=job_type,
        entity_type=entity_type,
        entity_id=entity_id,
        status='queued',
        payload=payload or {},
    )
    db.add(row)
    db.flush()
    return row


def start_job(db: Session, job_id: str) -> PlatformJob | None:
    row = db.get(PlatformJob, job_id)
    if row is None:
        return None
    row.status = 'running'
    row.started_at = row.started_at or datetime.now(UTC)
    row.error = None
    db.flush()
    return row


def complete_job(db: Session, job_id: str, result: dict[str, Any] | None = None) -> PlatformJob | None:
    row = db.get(PlatformJob, job_id)
    if row is None:
        return None
    row.status = 'completed'
    row.result = result or {}
    row.finished_at = datetime.now(UTC)
    row.error = None
    db.flush()
    return row


def fail_job(db: Session, job_id: str, error: str) -> PlatformJob | None:
    row = db.get(PlatformJob, job_id)
    if row is None:
        return None
    row.status = 'failed'
    row.error = error
    row.retry_count = int(row.retry_count or 0) + 1
    row.finished_at = datetime.now(UTC)
    db.flush()
    return row
