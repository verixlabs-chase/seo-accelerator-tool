from __future__ import annotations

from celery import current_app

WORKER_HEARTBEAT_KEY = "infra:worker:heartbeat"
SCHEDULER_HEARTBEAT_KEY = "infra:scheduler:heartbeat"


def inspect_active_queues(*, timeout_seconds: float = 0.5) -> dict | None:
    inspector = current_app.control.inspect(timeout=timeout_seconds)
    return inspector.active_queues()
