import uuid

from fastapi import Request


def envelope(request: Request, data: dict | None, error: dict | None = None) -> dict:
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    return {
        "data": data,
        "meta": {
            "request_id": request_id,
            "tenant_id": getattr(request.state, "tenant_id", None),
        },
        "error": error,
    }


def exception_envelope(request: Request, status_code: int, message: str, code: str, details: dict | None = None) -> dict:
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    return {
        "success": False,
        "errors": [{"code": code, "message": message, "details": details or {}}],
        "meta": {
            "request_id": request_id,
            "tenant_id": getattr(request.state, "tenant_id", None),
            "status_code": status_code,
        },
    }
