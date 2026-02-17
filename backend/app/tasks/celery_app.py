from celery import Celery
from celery.app.task import Task

from app.core.config import get_settings

settings = get_settings()


def create_celery_app() -> Celery:
    is_test_env = settings.app_env.lower() == "test"

    class LSOSTask(Task):
        def retry(self, *args, **kwargs):  # type: ignore[override]
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
