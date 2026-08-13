import re
import uuid

from fastapi import Request


_INTERNAL_SEARCH_SUPPLIER_URL = re.compile(
    r'https?://[^\s"\']*dataforseo[^\s"\']*',
    re.IGNORECASE,
)
_INTERNAL_SEARCH_SUPPLIER_NAME = re.compile(
    r"data[\s_-]*for[\s_-]*seo",
    re.IGNORECASE,
)


def customer_safe_api_value(value):
    if isinstance(value, dict):
        return {key: customer_safe_api_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [customer_safe_api_value(item) for item in value]
    if isinstance(value, tuple):
        return [customer_safe_api_value(item) for item in value]
    if not isinstance(value, str):
        return value
    sanitized = _INTERNAL_SEARCH_SUPPLIER_URL.sub("the search data service", value)
    return _INTERNAL_SEARCH_SUPPLIER_NAME.sub("the search data service", sanitized)


def public_data_source_label(provider_name: str) -> str:
    if _INTERNAL_SEARCH_SUPPLIER_NAME.search(provider_name):
        return "Search market data"
    return provider_name.replace("_", " ").strip().title() or "Configured data source"


def envelope(request: Request, data: dict | None, error: dict | None = None) -> dict:
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    return {
        "data": data,
        "meta": {
            "request_id": request_id,
            "tenant_id": getattr(request.state, "tenant_id", None),
        },
        "error": customer_safe_api_value(error),
    }


def exception_envelope(request: Request, status_code: int, message: str, code: str, details: dict | None = None) -> dict:
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    return {
        "success": False,
        "errors": [
            {
                "code": code,
                "message": customer_safe_api_value(message),
                "details": customer_safe_api_value(details or {}),
            }
        ],
        "meta": {
            "request_id": request_id,
            "tenant_id": getattr(request.state, "tenant_id", None),
            "status_code": status_code,
        },
    }
