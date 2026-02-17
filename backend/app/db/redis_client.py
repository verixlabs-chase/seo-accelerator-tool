from __future__ import annotations

import redis

from app.core.config import get_settings


def get_redis_client() -> redis.Redis | None:
    settings = get_settings()
    if settings.app_env.lower() == "test":
        return None
    return redis.Redis.from_url(settings.redis_url)
