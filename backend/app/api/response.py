from fastapi import Request


def envelope(request: Request, data: dict | None, error: dict | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "request_id": request.state.request_id,
            "tenant_id": getattr(request.state, "tenant_id", None),
        },
        "error": error,
    }

