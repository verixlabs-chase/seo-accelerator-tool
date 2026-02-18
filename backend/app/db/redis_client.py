from __future__ import annotations

import redis
from redis.exceptions import RedisError

from app.core.config import get_settings


def get_redis_client() -> redis.Redis | None:
    settings = get_settings()
    if settings.app_env.lower() == "test":
        return None
    client = redis.Redis.from_url(settings.redis_url)
    try:
        client.ping()
    except RedisError as exc:
        raise RuntimeError(f"Redis unavailable at {settings.redis_url}") from exc
    return client
