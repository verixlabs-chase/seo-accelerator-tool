from __future__ import annotations

from typing import Any

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

provider_calls_total = Counter(
    "provider_calls_total",
    "Total number of provider calls.",
    ["provider", "success"],
)

provider_call_duration_seconds = Histogram(
    "provider_call_duration_seconds",
    "Provider call duration in seconds.",
    ["provider"],
)

replay_executions_total = Counter(
    "replay_executions_total",
    "Total number of replay executions.",
    ["outcome", "drift"],
)

replay_execution_duration_seconds = Histogram(
    "replay_execution_duration_seconds",
    "Replay execution duration in seconds.",
    ["outcome"],
)

slow_queries_total = Counter(
    "slow_queries_total",
    "Total number of slow SQL queries.",
    ["band"],
)

traffic_fact_stale_campaigns_total = Counter(
    "traffic_fact_stale_campaigns_total",
    "Total number of stale traffic fact campaign detections.",
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

active_api_requests = Gauge(
    "active_api_requests",
    "Current number of active API requests.",
)

active_api_requests_by_tenant = Gauge(
    "active_api_requests_by_tenant",
    "Current number of active API requests per tenant.",
    ["tenant_id"],
)

worker_queue_depth = Gauge(
    "worker_queue_depth",
    "Current worker queue depth.",
    ["worker_name"],
)

worker_inflight_jobs = Gauge(
    "worker_inflight_jobs",
    "Current in-flight jobs per worker.",
    ["worker_name"],
)

graph_write_batch_size = Gauge(
    "graph_write_batch_size",
    "Number of knowledge graph edge writes flushed per batch.",
)

event_batch_latency_seconds = Histogram(
    "event_batch_latency_seconds",
    "Latency for processing event batches.",
    ["consumer_name"],
)

campaign_execution_lock_wait = Gauge(
    "campaign_execution_lock_wait",
    "Current campaign execution lock wait state.",
    ["campaign_id"],
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def internal_metrics_snapshot() -> dict[str, Any]:
    return {
        'active_api_requests': _gauge_value(active_api_requests),
        'worker_queue_depth': _collect_labeled_gauge(worker_queue_depth),
        'worker_inflight_jobs': _collect_labeled_gauge(worker_inflight_jobs),
        'graph_write_batch_size': _gauge_value(graph_write_batch_size),
        'campaign_execution_lock_wait': _collect_labeled_gauge(campaign_execution_lock_wait),
    }


def _gauge_value(metric: Gauge) -> float:
    return float(metric._value.get())  # type: ignore[attr-defined]


def _collect_labeled_gauge(metric: Gauge) -> dict[str, float]:
    samples: dict[str, float] = {}
    for sample in metric.collect()[0].samples:
        labels = '|'.join(f'{key}={value}' for key, value in sorted(sample.labels.items())) or 'default'
        samples[labels] = float(sample.value)
    return samples
