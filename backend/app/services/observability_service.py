from __future__ import annotations

from threading import Lock
from time import time
from typing import Any

from app.core.alert_thresholds import ALERT_THRESHOLDS

_lock = Lock()

_metrics: dict[str, Any] = {
    "worker_started": 0,
    "worker_success": 0,
    "worker_failed": 0,
    "queue_latency_ms_samples": [],
    "crawl_runs": 0,
    "crawl_failed_runs": 0,
    "entity_analysis_runs": 0,
}


def record_task_started(payload: dict) -> None:
    with _lock:
        _metrics["worker_started"] += 1
        queued_at = payload.get("queued_at")
        if isinstance(queued_at, (int, float)):
            latency_ms = max(0.0, (time() - float(queued_at)) * 1000.0)
            _metrics["queue_latency_ms_samples"].append(latency_ms)
            if len(_metrics["queue_latency_ms_samples"]) > 2000:
                _metrics["queue_latency_ms_samples"] = _metrics["queue_latency_ms_samples"][-1000:]


def record_task_finished(success: bool) -> None:
    with _lock:
        if success:
            _metrics["worker_success"] += 1
        else:
            _metrics["worker_failed"] += 1


def record_crawl_result(failed: bool) -> None:
    with _lock:
        _metrics["crawl_runs"] += 1
        if failed:
            _metrics["crawl_failed_runs"] += 1


def record_entity_analysis() -> None:
    with _lock:
        _metrics["entity_analysis_runs"] += 1


def snapshot() -> dict:
    with _lock:
        started = int(_metrics["worker_started"])
        success = int(_metrics["worker_success"])
        failed = int(_metrics["worker_failed"])
        crawl_runs = int(_metrics["crawl_runs"])
        crawl_failed = int(_metrics["crawl_failed_runs"])
        entity_analysis_runs = int(_metrics["entity_analysis_runs"])
        queue_samples = list(_metrics["queue_latency_ms_samples"])

    worker_success_rate = (success / started) if started > 0 else 1.0
    queue_latency_ms = (sum(queue_samples) / len(queue_samples)) if queue_samples else 0.0
    crawl_failure_rate = (crawl_failed / crawl_runs) if crawl_runs > 0 else 0.0
    queue_backlog_tasks = max(0, started - success - failed)

    queue_lag_threshold_ms = float(ALERT_THRESHOLDS.get("queue_lag_minutes", 5)) * 60_000.0
    crawl_failure_spike_threshold = float(ALERT_THRESHOLDS.get("crawl_failure_spike_percent", 10)) / 100.0
    alert_state = {
        "queue_lag": queue_latency_ms > queue_lag_threshold_ms,
        "crawl_failure_spike": crawl_failure_rate > crawl_failure_spike_threshold,
    }

    return {
        "slos": {
            "api_availability_target": 0.995,
            "worker_success_rate_target": 0.98,
            "queue_latency_seconds_target": 60,
            "crawl_success_rate_target": 0.95,
        },
        "metrics": {
            "worker_success_rate": round(worker_success_rate, 4),
            "queue_latency_ms": round(queue_latency_ms, 2),
            "queue_backlog_tasks": int(queue_backlog_tasks),
            "crawl_failure_rate": round(crawl_failure_rate, 4),
            "entity_analysis_runs": entity_analysis_runs,
        },
        "alerts": ALERT_THRESHOLDS,
        "alert_state": alert_state,
    }
