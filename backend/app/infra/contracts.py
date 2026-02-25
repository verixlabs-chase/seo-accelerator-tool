from __future__ import annotations

import sys

from celery import current_app

WORKER_HEARTBEAT_KEY = "infra:worker:heartbeat"
SCHEDULER_HEARTBEAT_KEY = "infra:scheduler:heartbeat"


def inspect_active_queues(*, timeout_seconds: float = 0.5) -> dict | None:
    celery_module = sys.modules.get("app.tasks.celery_app")
    celery_app = getattr(celery_module, "celery_app", None) if celery_module is not None else None
    app = celery_app if celery_app is not None else current_app
    inspector = app.control.inspect(timeout=timeout_seconds)
    return inspector.active_queues()
