from __future__ import annotations

import os
import threading
import time

from celery import Celery
from celery.app.task import Task
from celery.signals import beat_init, heartbeat_sent, task_postrun, task_prerun, worker_ready
from kombu import Queue

from app.core.config import get_settings
from app.core.metrics import celery_task_duration_seconds, tasks_in_progress
from app.db.redis_client import get_redis_client
from app.services.infra_service import SCHEDULER_HEARTBEAT_KEY, WORKER_HEARTBEAT_KEY

settings = get_settings()
_scheduler_heartbeat_started = False
_task_start_lock = threading.Lock()
_task_started_at: dict[str, float] = {}


def _queue_for_task_name(task_name: str | None) -> str:
    if not task_name:
        return "default_queue"
    if task_name.startswith("crawl."):
        return "crawl_queue"
    if task_name.startswith("rank."):
        return "rank_queue"
    if task_name.startswith("content."):
        return "content_queue"
    if task_name.startswith("authority."):
        return "authority_queue"
    return "default_queue"


def _resolve_prefetch_multiplier(default_multiplier: int) -> int:
    explicit_multiplier = os.getenv("CELERY_WORKER_PREFETCH_MULTIPLIER")
    if explicit_multiplier is not None:
        try:
            return max(1, int(explicit_multiplier))
        except ValueError:
            return max(1, int(default_multiplier))

    profile = os.getenv("CELERY_WORKER_PROFILE", "default").strip().lower()
    profile_defaults = {
        "crawl": 1,
        "rank": 1,
        "content": 2,
        "authority": 1,
        "default": 1,
    }
    if profile in profile_defaults:
        return profile_defaults[profile]
    return max(1, int(default_multiplier))


def _publish_heartbeat(key: str) -> None:
    client = get_redis_client()
    if client is None:
        return
    client.setex(key, 120, str(int(time.time())))


@worker_ready.connect
def _worker_ready_heartbeat(**_kwargs) -> None:
    _publish_heartbeat(WORKER_HEARTBEAT_KEY)


@heartbeat_sent.connect
def _worker_heartbeat_sent(**_kwargs) -> None:
    _publish_heartbeat(WORKER_HEARTBEAT_KEY)


@beat_init.connect
def _scheduler_heartbeat_loop(**_kwargs) -> None:
    global _scheduler_heartbeat_started
    if _scheduler_heartbeat_started:
        return
    _scheduler_heartbeat_started = True

    def _loop() -> None:
        while True:
            _publish_heartbeat(SCHEDULER_HEARTBEAT_KEY)
            time.sleep(30)

    thread = threading.Thread(target=_loop, name="scheduler-heartbeat", daemon=True)
    thread.start()


@task_prerun.connect
def _record_task_start(task_id=None, **_kwargs) -> None:
    if not task_id:
        return
    task_name = getattr(_kwargs.get("task"), "name", None)
    queue_name = _queue_for_task_name(task_name)
    with _task_start_lock:
        _task_started_at[task_id] = time.perf_counter()
    tasks_in_progress.labels(queue_name=queue_name).inc()


@task_postrun.connect
def _record_task_duration(task_id=None, task=None, **_kwargs) -> None:
    if not task_id:
        return
    with _task_start_lock:
        started_at = _task_started_at.pop(task_id, None)
    if started_at is None:
        return
    duration_seconds = time.perf_counter() - started_at
    task_name = getattr(task, "name", None) or "unknown"
    queue_name = _queue_for_task_name(getattr(task, "name", None))
    tasks_in_progress.labels(queue_name=queue_name).dec()
    celery_task_duration_seconds.labels(task_name=task_name, queue_name=queue_name).observe(duration_seconds)


def create_celery_app() -> Celery:
    is_test_env = settings.app_env.lower() == "test"
    if not is_test_env:
        # Fail fast when Redis is unavailable in non-test environments.
        get_redis_client()

    class LSOSTask(Task):
        def retry(self, *args, **kwargs):
            if is_test_env:
                exc = kwargs.get("exc")
                if exc is not None:
                    raise exc
                raise RuntimeError("Retry requested during tests without an underlying exception.")
            return super().retry(*args, **kwargs)

    if is_test_env:
        broker = "memory://"
        backend = "cache+memory://"
        task_always_eager = True
        task_eager_propagates = True
    else:
        broker = settings.celery_broker_url
        backend = settings.celery_result_backend
        task_always_eager = settings.celery_task_always_eager
        task_eager_propagates = settings.celery_task_eager_propagates

    celery = Celery("lsos", broker=broker, backend=backend)
    celery.Task = LSOSTask
    celery.conf.task_always_eager = task_always_eager
    celery.conf.task_eager_propagates = task_eager_propagates
    celery.conf.worker_prefetch_multiplier = _resolve_prefetch_multiplier(settings.celery_worker_prefetch_multiplier)

    celery.conf.task_default_queue = "default_queue"
    celery.conf.task_queues = (
        Queue("crawl_queue"),
        Queue("rank_queue"),
        Queue("content_queue"),
        Queue("authority_queue"),
        Queue("default_queue"),
    )
    celery.conf.task_routes = {
        "crawl.*": {"queue": "crawl_queue"},
        "rank.*": {"queue": "rank_queue"},
        "content.*": {"queue": "content_queue"},
        "authority.*": {"queue": "authority_queue"},
        "*": {"queue": "default_queue"},
    }
    celery.conf.timezone = "UTC"
    celery.autodiscover_tasks(["app.tasks"])
    return celery


celery_app = create_celery_app()
