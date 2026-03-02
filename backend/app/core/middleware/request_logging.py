from __future__ import annotations

import logging
from time import monotonic
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.operational_telemetry_service import record_api_request


logger = logging.getLogger("lsos.api")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        started_at = monotonic()
        response = await call_next(request)
        duration_ms = (monotonic() - started_at) * 1000.0
        route = request.scope.get("route")
        route_path = getattr(route, "path", None) or request.url.path
        response.headers.setdefault("X-Request-ID", request_id)
        record_api_request(
            route=route_path,
            org_id=getattr(request.state, "organization_id", None),
            duration_ms=duration_ms,
            status_code=response.status_code,
        )
        logger.info(
            "api_request",
            extra={
                "event": "api_request",
                "request_id": request_id,
                "tenant_id": getattr(request.state, "tenant_id", None),
                "organization_id": getattr(request.state, "organization_id", None),
                "method": request.method,
                "path": request.url.path,
                "route": route_path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response
