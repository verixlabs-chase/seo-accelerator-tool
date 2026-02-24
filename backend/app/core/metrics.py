from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest


http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests.",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "path"],
)

celery_task_duration_seconds = Histogram(
    "celery_task_duration_seconds",
    "Celery task duration in seconds.",
    ["task_name", "queue_name"],
)

queue_depth = Gauge(
    "queue_depth",
    "Current queue depth per queue.",
    ["queue_name"],
)

active_workers = Gauge(
    "active_workers",
    "Active worker count per queue.",
    ["queue_name"],
)

tasks_in_progress = Gauge(
    "tasks_in_progress",
    "Number of tasks currently in progress per queue.",
    ["queue_name"],
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
