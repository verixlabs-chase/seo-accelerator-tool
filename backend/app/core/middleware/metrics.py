from __future__ import annotations

from time import monotonic

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.metrics import http_request_duration_seconds, http_requests_total


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started_at = monotonic()
        response = await call_next(request)
        duration = monotonic() - started_at
        route = request.scope.get("route")
        route_path = getattr(route, "path", None) or "unmatched"
        http_requests_total.labels(
            method=request.method,
            path=route_path,
            status=str(response.status_code),
        ).inc()
        http_request_duration_seconds.labels(
            method=request.method,
            path=route_path,
        ).observe(duration)
        return response
