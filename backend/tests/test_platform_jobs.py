import uuid

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
