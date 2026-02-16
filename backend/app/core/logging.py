import json
import logging
import uuid
from typing import Callable

from fastapi import Request, Response


logger = logging.getLogger("lsos.api")


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")


async def request_context_middleware(request: Request, call_next: Callable) -> Response:
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    tenant_id = getattr(request.state, "tenant_id", None)
    logger.info(
        json.dumps(
            {
                "event": "request.started",
                "request_id": request_id,
                "tenant_id": tenant_id,
                "method": request.method,
                "path": request.url.path,
            }
        )
    )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        json.dumps(
            {
                "event": "request.finished",
                "request_id": request_id,
                "tenant_id": getattr(request.state, "tenant_id", None),
                "status_code": response.status_code,
            }
        )
    )
    return response

