from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


logger = logging.getLogger("lsos.api")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        started_at = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        response.headers.setdefault("X-Request-ID", request_id)
        logger.info(
            "http.request",
            extra={
                "request_id": request_id,
                "tenant_id": getattr(request.state, "tenant_id", None),
                "organization_id": getattr(request.state, "organization_id", None),
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
