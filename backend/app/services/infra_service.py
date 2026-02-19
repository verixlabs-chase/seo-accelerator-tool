from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Callable

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import SessionLocal

WORKER_HEARTBEAT_KEY = "infra:worker:heartbeat"
SCHEDULER_HEARTBEAT_KEY = "infra:scheduler:heartbeat"
REDIS_HEALTHCHECK_TIMEOUT_SECONDS = 0.2
_REDIS_PROBE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="infra-redis-probe")


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
