from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Callable

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from sqlalchemy import text

from app.core.config import get_settings
from app.core.metrics import active_workers, queue_depth
from app.db.session import SessionLocal

WORKER_HEARTBEAT_KEY = "infra:worker:heartbeat"
SCHEDULER_HEARTBEAT_KEY = "infra:scheduler:heartbeat"
REDIS_HEALTHCHECK_TIMEOUT_SECONDS = 0.2
_REDIS_PROBE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="infra-redis-probe")
_BACKPRESSURE_WORKLOAD_QUEUES: dict[str, str] = {
    "crawl": "crawl_queue",
    "content": "content_queue",
}


def _healthcheck_redis_client() -> redis.Redis | None:
    settings = get_settings()
    if settings.app_env.lower() == "test":
        return None
    return redis.Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=REDIS_HEALTHCHECK_TIMEOUT_SECONDS,
        socket_timeout=REDIS_HEALTHCHECK_TIMEOUT_SECONDS,
        retry_on_timeout=False,
        retry=Retry(NoBackoff(), 0),
    )


def _run_redis_probe(probe: Callable[[], bool]) -> bool:
    future = _REDIS_PROBE_EXECUTOR.submit(probe)
    try:
        return bool(future.result(timeout=REDIS_HEALTHCHECK_TIMEOUT_SECONDS))
    except FutureTimeoutError:
        future.cancel()
        return False
    except Exception:
        return False


def _run_redis_probe_value(probe: Callable[[], Any], default: Any) -> Any:
    future = _REDIS_PROBE_EXECUTOR.submit(probe)
    try:
        return future.result(timeout=REDIS_HEALTHCHECK_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        future.cancel()
        return default
    except Exception:
        return default


def db_connected() -> bool:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        db.close()


def redis_connected() -> bool:
    def _probe() -> bool:
        client = _healthcheck_redis_client()
        if client is None:
            return False
        return bool(client.ping())

    return _run_redis_probe(_probe)


def worker_active() -> bool:
    def _probe() -> bool:
        client = _healthcheck_redis_client()
        if client is None:
            return False
        if client.exists(WORKER_HEARTBEAT_KEY) != 1:
            return False
        ttl = client.ttl(WORKER_HEARTBEAT_KEY)
        if not isinstance(ttl, int):
            return False
        return ttl > 0

    return _run_redis_probe(_probe)


def scheduler_active() -> bool:
    def _probe() -> bool:
        client = _healthcheck_redis_client()
        if client is None:
            return False
        return client.exists(SCHEDULER_HEARTBEAT_KEY) == 1

    return _run_redis_probe(_probe)


def proxy_configured() -> bool:
    settings = get_settings()
    return bool((settings.proxy_provider_config_json or "").strip())


def smtp_configured() -> bool:
    settings = get_settings()
    required_values = [settings.smtp_host, settings.smtp_from_email]
    return all(bool(str(v).strip()) for v in required_values)


def celery_queue_status() -> dict[str, object]:
    try:
        from app.tasks.celery_app import celery_app

        inspector = celery_app.control.inspect(timeout=0.5)
        active = inspector.active_queues() or {}
    except Exception:
        return {"active_queues": [], "worker_count_per_queue": {}}

    queue_worker_counts: dict[str, int] = {}
    for worker_queues in active.values():
        for queue_info in worker_queues:
            queue_name = str(queue_info.get("name", "")).strip()
            if not queue_name:
                continue
            queue_worker_counts[queue_name] = queue_worker_counts.get(queue_name, 0) + 1
    for queue_name, worker_count in queue_worker_counts.items():
        active_workers.labels(queue_name=queue_name).set(worker_count)
        queue_depth_count(queue_name)
    return {
        "active_queues": sorted(queue_worker_counts.keys()),
        "worker_count_per_queue": queue_worker_counts,
    }


def queue_depth_count(queue_name: str) -> int | None:
    def _probe() -> int | None:
        client = _healthcheck_redis_client()
        if client is None:
            return None
        depth = client.llen(queue_name)
        return int(depth)

    depth_value = _run_redis_probe_value(_probe, None)
    if isinstance(depth_value, int):
        queue_depth.labels(queue_name=queue_name).set(depth_value)
        return depth_value
    return None


def queue_backpressure_active(workload: str) -> bool:
    settings = get_settings()
    if not settings.queue_backpressure_enabled:
        return False
    queue_name = _BACKPRESSURE_WORKLOAD_QUEUES.get(workload)
    if queue_name is None:
        return False
    depth = queue_depth_count(queue_name)
    if depth is None:
        # Fail open when Redis queue depth is unavailable.
        return False
    return depth > int(settings.queue_backpressure_threshold)
