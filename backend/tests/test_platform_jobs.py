import uuid
from datetime import UTC, datetime, timedelta

from app.models.platform_job import PlatformJob
from app.services import job_service


def test_platform_job_lifecycle(db_session) -> None:
    job = job_service.create_job(
        db_session,
        job_type='crawl.execute',
        entity_type='campaign',
        entity_id=str(uuid.uuid4()),
        payload={'k': 'v'},
    )
    db_session.commit()

    started = job_service.start_job(db_session, job.id)
    assert started is not None
    assert started.status == 'running'

    completed = job_service.complete_job(db_session, job.id, result={'ok': True})
    db_session.commit()
    assert completed is not None
    assert completed.status == 'completed'
    assert completed.result == {'ok': True}


def test_platform_job_fail_increments_retry_count(db_session) -> None:
    job = job_service.create_job(
        db_session,
        job_type='report.generate',
        entity_type='campaign',
        entity_id=str(uuid.uuid4()),
        payload={},
    )
    db_session.commit()

    failed = job_service.fail_job(db_session, job.id, error='failure')
    db_session.commit()

    assert failed is not None
    assert failed.status == 'failed'
    assert failed.retry_count == 1

    row = db_session.get(PlatformJob, job.id)
    assert row is not None
    assert row.error == 'failure'


def test_platform_job_idempotency_key_returns_existing_job(db_session) -> None:
    idempotency_key = f"test-job:{uuid.uuid4()}"
    first = job_service.create_job(
        db_session,
        tenant_id=str(uuid.uuid4()),
        job_type="reporting.process_schedule",
        entity_type="campaign",
        entity_id=str(uuid.uuid4()),
        idempotency_key=idempotency_key,
        payload={"attempt": 1},
    )
    db_session.commit()

    second = job_service.create_job(
        db_session,
        tenant_id=first.tenant_id,
        job_type="reporting.process_schedule",
        entity_type="campaign",
        entity_id=first.entity_id,
        idempotency_key=idempotency_key,
        payload={"attempt": 2},
    )

    assert second.id == first.id
    assert second.payload == {"attempt": 1}
    assert db_session.query(PlatformJob).filter(
        PlatformJob.idempotency_key == idempotency_key
    ).count() == 1


def test_claim_jobs_skips_future_work_and_recovers_expired_lease(db_session) -> None:
    now = datetime.now(UTC)
    future = job_service.create_job(
        db_session,
        job_type="future",
        entity_type="generic",
        entity_id=None,
        available_at=now + timedelta(hours=1),
    )
    expired = job_service.create_job(
        db_session,
        job_type="expired",
        entity_type="generic",
        entity_id=None,
        available_at=now - timedelta(minutes=5),
    )
    expired.status = job_service.JOB_STATUS_RUNNING
    expired.locked_by = "old-worker"
    expired.locked_at = now - timedelta(minutes=10)
    expired.lease_expires_at = now - timedelta(minutes=1)
    db_session.commit()

    claimed = job_service.claim_jobs(
        db_session,
        worker_id="new-worker",
        limit=10,
        lease_seconds=60,
        now=now,
    )
    db_session.commit()

    assert [row.id for row in claimed] == [expired.id]
    assert claimed[0].locked_by == "new-worker"
    assert claimed[0].lease_expires_at is not None
    assert future.status == job_service.JOB_STATUS_QUEUED


def test_record_job_failure_requeues_then_dead_letters(db_session) -> None:
    job = job_service.create_job(
        db_session,
        job_type="test.failure",
        entity_type="generic",
        entity_id=None,
        max_retries=1,
    )
    db_session.commit()

    first = job_service.record_job_failure(
        db_session,
        job.id,
        error="temporary",
        retry_base_seconds=1,
    )
    db_session.commit()
    assert first is not None
    assert first.status == job_service.JOB_STATUS_QUEUED
    assert first.retry_count == 1

    second = job_service.record_job_failure(
        db_session,
        job.id,
        error="terminal",
        retry_base_seconds=1,
    )
    db_session.commit()
    assert second is not None
    assert second.status == job_service.JOB_STATUS_DEAD_LETTER
    assert second.retry_count == 2


def test_release_jobs_returns_unprocessed_claims_to_queue(db_session) -> None:
    job = job_service.create_job(
        db_session,
        job_type="test.deferred",
        entity_type="generic",
        entity_id=None,
    )
    db_session.commit()

    claimed = job_service.claim_jobs(
        db_session,
        worker_id="short-invocation",
        limit=1,
        lease_seconds=60,
    )
    db_session.commit()
    assert [row.id for row in claimed] == [job.id]

    released = job_service.release_jobs(
        db_session,
        job_ids=[job.id],
        worker_id="short-invocation",
    )
    db_session.commit()

    assert released == 1
    assert job.status == job_service.JOB_STATUS_QUEUED
    assert job.locked_by is None
    assert job.lease_expires_at is None
