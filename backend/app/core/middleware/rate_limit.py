from __future__ import annotations

import logging
import time

from fastapi import Request
from fastapi.responses import JSONResponse
import redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware


_WINDOW_SECONDS = 60.0
logger = logging.getLogger("lsos.api.rate_limit")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, enabled: bool, requests_per_minute: int, redis_url: str) -> None:
        super().__init__(app)
        self._enabled = enabled
        self._requests_per_minute = max(1, int(requests_per_minute))
        self._redis = redis.Redis.from_url(redis_url)

    async def dispatch(self, request: Request, call_next):
        if not self._enabled:
            return await call_next(request)

        client_ip = request.client.host if request.client is not None and request.client.host else "unknown"
        now = time.time()
        cutoff = now - _WINDOW_SECONDS
        key = f"rate_limit:{client_ip}"
        try:
            pipeline = self._redis.pipeline(transaction=True)
            pipeline.zadd(key, {str(now): now})
            pipeline.zremrangebyscore(key, 0, cutoff)
            pipeline.zcard(key)
            pipeline.expire(key, 120)
            _added, _removed, request_count, _expiry = pipeline.execute()
        except RedisError:
            logger.warning("rate_limit_redis_unavailable_fail_open")
            return await call_next(request)

        if int(request_count) > self._requests_per_minute:
            logger.debug("rate limit exceeded for client ip")
            return JSONResponse(
                status_code=429,
                content={"message": "Rate limit exceeded", "reason_code": "rate_limit_exceeded"},
            )
        return await call_next(request)
