from __future__ import annotations

import logging
import time
from itertools import count
from threading import RLock
from typing import Any

from app.core.config import get_settings
from app.core.metrics import queue_depth, worker_inflight_jobs, worker_queue_depth
from app.events.event_types import EventType

logger = logging.getLogger('lsos.intelligence.queue')

_FAILED_JOBS: dict[str, dict[str, Any]] = {}
_JOB_COUNTER = count(1)
_QUEUE_LOCK = RLock()
_QUEUE_DEPTH: dict[str, int] = {}
_WORKER_INFLIGHT: dict[str, int] = {}
_RETRY_BACKOFF_SECONDS = (0.01, 0.02, 0.04)


def dispatch_worker_job(worker_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    max_queue_depth = max(1, int(settings.max_queue_depth))
    max_worker_inflight = max(1, int(settings.max_worker_inflight))

    for attempt, delay in enumerate((0.0, *_RETRY_BACKOFF_SECONDS), start=1):
        if delay:
            time.sleep(delay)
        if _can_dispatch(worker_name, max_queue_depth=max_queue_depth, max_worker_inflight=max_worker_inflight):
            return _dispatch(worker_name, payload, settings.app_env.lower() == 'test')
        logger.warning(
            'worker_queue_backpressure',
            extra={
                'worker_name': worker_name,
                'attempt': attempt,
                'queue_depth': _QUEUE_DEPTH.get(worker_name, 0),
                'worker_inflight': _WORKER_INFLIGHT.get(worker_name, 0),
            },
        )

    return {
        'worker': worker_name,
        'mode': 'rejected',
        'status': 'failed',
        'error': 'backpressure_limit_exceeded',
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
    with _QUEUE_LOCK:
        _QUEUE_DEPTH.clear()
        _WORKER_INFLIGHT.clear()
    _sync_metrics()


def queue_stats() -> dict[str, dict[str, int]]:
    with _QUEUE_LOCK:
        return {
            'queue_depth': {key: int(value) for key, value in _QUEUE_DEPTH.items()},
            'worker_inflight_jobs': {key: int(value) for key, value in _WORKER_INFLIGHT.items()},
        }


def _dispatch(worker_name: str, payload: dict[str, Any], use_inline: bool) -> dict[str, Any]:
    _increment_queue(worker_name)
    try:
        if use_inline:
            return _run_inline(worker_name, payload)

        from app.tasks.intelligence_tasks import run_intelligence_worker_task

        task = run_intelligence_worker_task.delay(worker_name=worker_name, payload=payload)
        return {
            'worker': worker_name,
            'mode': 'queued',
            'status': 'queued',
            'task_id': task.id,
        }
    finally:
        _decrement_queue(worker_name)


def _can_dispatch(worker_name: str, *, max_queue_depth: int, max_worker_inflight: int) -> bool:
    with _QUEUE_LOCK:
        depth = _QUEUE_DEPTH.get(worker_name, 0)
        inflight = _WORKER_INFLIGHT.get(worker_name, 0)
    return depth < max_queue_depth and inflight < max_worker_inflight


def _run_inline(worker_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    from app.intelligence.workers import run_worker

    job_id = f'job-{next(_JOB_COUNTER)}'
    _increment_inflight(worker_name)
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
    finally:
        _decrement_inflight(worker_name)
    return {
        'job_id': job_id,
        'worker': worker_name,
        'mode': 'inline',
        'status': 'succeeded',
        'result': result,
    }


def _increment_queue(worker_name: str) -> None:
    with _QUEUE_LOCK:
        _QUEUE_DEPTH[worker_name] = _QUEUE_DEPTH.get(worker_name, 0) + 1
    _sync_metrics()


def _decrement_queue(worker_name: str) -> None:
    with _QUEUE_LOCK:
        _QUEUE_DEPTH[worker_name] = max(0, _QUEUE_DEPTH.get(worker_name, 0) - 1)
    _sync_metrics()


def _increment_inflight(worker_name: str) -> None:
    with _QUEUE_LOCK:
        _WORKER_INFLIGHT[worker_name] = _WORKER_INFLIGHT.get(worker_name, 0) + 1
    _sync_metrics()


def _decrement_inflight(worker_name: str) -> None:
    with _QUEUE_LOCK:
        _WORKER_INFLIGHT[worker_name] = max(0, _WORKER_INFLIGHT.get(worker_name, 0) - 1)
    _sync_metrics()


def _sync_metrics() -> None:
    with _QUEUE_LOCK:
        keys = set(_QUEUE_DEPTH) | set(_WORKER_INFLIGHT)
        for worker_name in keys:
            depth = _QUEUE_DEPTH.get(worker_name, 0)
            inflight = _WORKER_INFLIGHT.get(worker_name, 0)
            queue_depth.labels(queue_name=worker_name).set(depth)
            worker_queue_depth.labels(worker_name=worker_name).set(depth)
            worker_inflight_jobs.labels(worker_name=worker_name).set(inflight)
