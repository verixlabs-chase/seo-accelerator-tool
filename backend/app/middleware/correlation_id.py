from __future__ import annotations

from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.correlation import clear_correlation_id, set_correlation_id


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get('X-Correlation-ID') or request.headers.get('X-Request-ID') or str(uuid4())
        request.state.correlation_id = correlation_id
        set_correlation_id(correlation_id)
        try:
            response = await call_next(request)
        finally:
            clear_correlation_id()
        response.headers.setdefault('X-Correlation-ID', correlation_id)
        return response
