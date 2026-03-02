from __future__ import annotations

import logging
from collections import deque
from threading import Lock
from time import monotonic

from app.core.metrics import (
    provider_call_duration_seconds,
    provider_calls_total,
    replay_execution_duration_seconds,
    replay_executions_total,
    slow_queries_total,
)


logger = logging.getLogger("lsos.operations")

NON_PROVIDER_P95_MS = 250.0
NON_PROVIDER_P99_MS = 600.0
NON_PROVIDER_ERROR_RATE_TARGET = 0.01
PROVIDER_P95_MS = 900.0
PROVIDER_ERROR_RATE_TARGET = 0.03
REPLAY_FAILURE_RATE_TARGET = 0.005
DB_SLOW_QUERY_MS = 200.0
DB_CRITICAL_QUERY_MS = 500.0
QUEUE_DEPTH_SOFT_CEILING = 100
QUEUE_DEPTH_HARD_CEILING = 250
_TASK_P95_BANDS_MS = {
    "fast": 250.0,
    "standard": 1000.0,
    "heavy": 5000.0,
}
_WINDOW_SECONDS = 300.0
_MAX_API_SAMPLES = 512
_MAX_PROVIDER_SAMPLES = 512
_MAX_REPLAY_SAMPLES = 256
_MAX_SLOW_QUERY_SAMPLES = 256

_lock = Lock()
_api_samples: deque[tuple[float, float, int]] = deque(maxlen=_MAX_API_SAMPLES)
_provider_samples: dict[str, deque[tuple[float, float, bool]]] = {}
_replay_samples: deque[tuple[float, float, bool, bool]] = deque(maxlen=_MAX_REPLAY_SAMPLES)
_slow_queries: deque[tuple[float, float]] = deque(maxlen=_MAX_SLOW_QUERY_SAMPLES)
_queue_depth_by_name: dict[str, int] = {}


def reset_operational_telemetry() -> None:
    with _lock:
        _api_samples.clear()
        _provider_samples.clear()
        _replay_samples.clear()
        _slow_queries.clear()
        _queue_depth_by_name.clear()


def record_api_request(*, route: str, org_id: str | None, duration_ms: float, status_code: int) -> None:
    now = monotonic()
    with _lock:
        _api_samples.append((now, float(duration_ms), int(status_code)))


def record_service_operation(
    *,
    service: str,
    operation: str,
    duration_ms: float,
    success: bool,
    organization_id: str | None = None,
) -> None:
    logger.info(
        "service_operation",
        extra={
            "event": "service_operation",
            "service": service,
            "operation": operation,
            "organization_id": organization_id,
            "duration_ms": round(float(duration_ms), 2),
            "success": bool(success),
        },
    )


def record_provider_call(*, provider: str, duration_ms: float, success: bool) -> None:
    now = monotonic()
    with _lock:
        bucket = _provider_samples.setdefault(provider, deque(maxlen=_MAX_PROVIDER_SAMPLES))
        bucket.append((now, float(duration_ms), bool(success)))
    provider_calls_total.labels(provider=provider, success=str(bool(success)).lower()).inc()
    provider_call_duration_seconds.labels(provider=provider).observe(float(duration_ms) / 1000.0)
    logger.info(
        "provider_call",
        extra={
            "event": "provider_call",
            "provider": provider,
            "duration_ms": round(float(duration_ms), 2),
            "success": bool(success),
        },
    )


def record_queue_depth_snapshot(*, queue_name: str, depth: int) -> None:
    with _lock:
        _queue_depth_by_name[queue_name] = int(depth)
    logger.info(
        "queue_depth_snapshot",
        extra={
            "event": "queue_depth_snapshot",
            "queue": queue_name,
            "depth": int(depth),
        },
    )


def record_replay_execution(*, duration_ms: float, success: bool, drift_detected: bool) -> None:
    now = monotonic()
    with _lock:
        _replay_samples.append((now, float(duration_ms), bool(success), bool(drift_detected)))
    outcome = "success" if success else "failed"
    replay_executions_total.labels(outcome=outcome, drift=str(bool(drift_detected)).lower()).inc()
    replay_execution_duration_seconds.labels(outcome=outcome).observe(float(duration_ms) / 1000.0)
    logger.info(
        "replay_execution",
        extra={
            "event": "replay_execution",
            "duration_ms": round(float(duration_ms), 2),
            "success": bool(success),
            "drift_detected": bool(drift_detected),
        },
    )


def record_query_duration(*, statement: str, duration_ms: float) -> None:
    if float(duration_ms) < DB_SLOW_QUERY_MS:
        return

    now = monotonic()
    with _lock:
        _slow_queries.append((now, float(duration_ms)))

    band = "critical" if float(duration_ms) >= DB_CRITICAL_QUERY_MS else "slow"
    slow_queries_total.labels(band=band).inc()
    logger.warning(
        "slow_query",
        extra={
            "event": "slow_query",
            "duration_ms": round(float(duration_ms), 2),
            "query_band": band,
            "statement": _normalize_statement(statement),
        },
    )


def snapshot_operational_health() -> dict[str, object]:
    now = monotonic()
    with _lock:
        api_samples = [sample for sample in _api_samples if now - sample[0] <= _WINDOW_SECONDS]
        provider_samples = {
            name: [sample for sample in samples if now - sample[0] <= _WINDOW_SECONDS]
            for name, samples in _provider_samples.items()
        }
        replay_samples = [sample for sample in _replay_samples if now - sample[0] <= _WINDOW_SECONDS]
        slow_queries = [sample for sample in _slow_queries if now - sample[0] <= _WINDOW_SECONDS]
        queue_depth = dict(_queue_depth_by_name)

    api_latencies = [sample[1] for sample in api_samples]
    api_errors = [sample for sample in api_samples if sample[2] >= 500]

    provider_error_bands: list[dict[str, object]] = []
    for provider, samples in sorted(provider_samples.items()):
        latencies = [sample[1] for sample in samples]
        failures = [sample for sample in samples if not sample[2]]
        provider_error_bands.append(
            {
                "provider": provider,
                "calls": len(samples),
                "failure_rate": round((len(failures) / len(samples)) if samples else 0.0, 4),
                "p95_latency_ms": round(_percentile(latencies, 95), 2),
            }
        )

    replay_failures = [sample for sample in replay_samples if not sample[2]]
    replay_drifts = [sample for sample in replay_samples if sample[3]]

    return {
        "slo_targets": {
            "api": {
                "p95_ms": NON_PROVIDER_P95_MS,
                "p99_ms": NON_PROVIDER_P99_MS,
                "error_rate": NON_PROVIDER_ERROR_RATE_TARGET,
            },
            "provider": {
                "p95_ms": PROVIDER_P95_MS,
                "error_rate": PROVIDER_ERROR_RATE_TARGET,
            },
            "db": {
                "slow_query_ms": DB_SLOW_QUERY_MS,
                "critical_query_ms": DB_CRITICAL_QUERY_MS,
            },
            "queue": {
                "soft_ceiling": QUEUE_DEPTH_SOFT_CEILING,
                "hard_ceiling": QUEUE_DEPTH_HARD_CEILING,
                "task_p95_bands_ms": dict(_TASK_P95_BANDS_MS),
            },
            "replay": {
                "drift_tolerance": 0,
                "execution_failure_rate": REPLAY_FAILURE_RATE_TARGET,
            },
        },
        "recent_p95_latency_ms": round(_percentile(api_latencies, 95), 2),
        "recent_p99_latency_ms": round(_percentile(api_latencies, 99), 2),
        "recent_error_rate": round((len(api_errors) / len(api_samples)) if api_samples else 0.0, 4),
        "queue_depth": queue_depth,
        "provider_error_bands": provider_error_bands,
        "replay": {
            "recent_runs": len(replay_samples),
            "drift_status": "drift_detected" if replay_drifts else "clean",
            "execution_failure_rate": round((len(replay_failures) / len(replay_samples)) if replay_samples else 0.0, 4),
        },
        "slow_query_count": len(slow_queries),
    }


def _normalize_statement(statement: str) -> str:
    compact = " ".join(statement.split())
    return compact[:160]


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = ((percentile / 100.0) * (len(ordered) - 1))
    lower = int(rank)
    upper = min(len(ordered) - 1, lower + 1)
    weight = rank - lower
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * weight)
