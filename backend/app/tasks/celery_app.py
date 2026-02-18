from __future__ import annotations

import threading
import time

from celery import Celery
from celery.app.task import Task
from celery.signals import beat_init, heartbeat_sent, worker_ready

from app.core.config import get_settings
from app.db.redis_client import get_redis_client
from app.services.infra_service import SCHEDULER_HEARTBEAT_KEY, WORKER_HEARTBEAT_KEY

settings = get_settings()
_scheduler_heartbeat_started = False


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

    celery.conf.task_default_queue = "default"
    celery.conf.timezone = "UTC"
    celery.autodiscover_tasks(["app.tasks"])
    return celery


celery_app = create_celery_app()
