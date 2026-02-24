from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_request_body_bytes: int) -> None:
        super().__init__(app)
        self._max_request_body_bytes = max_request_body_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                parsed_length = int(content_length)
            except (TypeError, ValueError):
                parsed_length = None
            if parsed_length is not None and parsed_length > self._max_request_body_bytes:
                return JSONResponse(
                    status_code=413,
                    content={"message": "Payload too large", "reason_code": "payload_too_large"},
                )
        return await call_next(request)
