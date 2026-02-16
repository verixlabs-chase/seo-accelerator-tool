from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "lsos",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.task_default_queue = "default"
celery_app.conf.timezone = "UTC"
celery_app.autodiscover_tasks(["app.tasks"])

