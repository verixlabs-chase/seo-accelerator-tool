from __future__ import annotations

from itertools import count
from typing import Any

from app.events.event_types import EventType

_FAILED_JOBS: dict[str, dict[str, Any]] = {}
_JOB_COUNTER = count(1)


def dispatch_worker_job(worker_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.app_env.lower() == 'test':
        return _run_inline(worker_name, payload)

    from app.tasks.intelligence_tasks import run_intelligence_worker_task

    task = run_intelligence_worker_task.delay(worker_name=worker_name, payload=payload)
    return {
        'worker': worker_name,
        'mode': 'queued',
        'status': 'queued',
        'task_id': task.id,
    }


def dispatch_worker(worker_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return dispatch_worker_job(worker_name, payload)


def enqueue_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if event_type == EventType.OUTCOME_RECORDED.value:
        return dispatch_worker_job('learning', payload)
    if event_type == EventType.EXPERIMENT_COMPLETED.value:
        return dispatch_worker_job('experiment', payload)
    raise ValueError(f'Unsupported worker queue event: {event_type}')


def enqueue_learning_event(payload: dict[str, Any]) -> dict[str, Any]:
    return enqueue_event(EventType.OUTCOME_RECORDED.value, payload)


def enqueue_experiment_event(payload: dict[str, Any]) -> dict[str, Any]:
    return enqueue_event(EventType.EXPERIMENT_COMPLETED.value, payload)


def list_failed_jobs() -> list[dict[str, Any]]:
    return [dict(item) for item in _FAILED_JOBS.values()]


def retry_failed_job(job_id: str) -> dict[str, Any]:
    record = _FAILED_JOBS.get(job_id)
    if record is None:
        raise KeyError(job_id)
    result = _run_inline(str(record['worker']), dict(record['payload']))
    if result.get('status') == 'succeeded':
        _FAILED_JOBS.pop(job_id, None)
    return result


def reset_queue_state() -> None:
    _FAILED_JOBS.clear()


def _run_inline(worker_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    from app.intelligence.workers import run_worker

    job_id = f'job-{next(_JOB_COUNTER)}'
    try:
        result = run_worker(worker_name, payload)
    except Exception as exc:  # noqa: BLE001
        record = {
            'job_id': job_id,
            'worker': worker_name,
            'payload': dict(payload),
            'status': 'failed',
            'error': str(exc),
        }
        _FAILED_JOBS[job_id] = record
        return {
            'job_id': job_id,
            'worker': worker_name,
            'mode': 'inline',
            'status': 'failed',
            'error': str(exc),
        }
    return {
        'job_id': job_id,
        'worker': worker_name,
        'mode': 'inline',
        'status': 'succeeded',
        'result': result,
    }
