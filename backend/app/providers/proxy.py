from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger("lsos.provider.proxy")
_SENSITIVE_PROXY_KEYS = {"api_key", "apikey", "authorization", "password", "token", "secret", "username"}


class ProxyRotationAdapter(Protocol):
    def next_proxy(self) -> str | None:
        ...


class NullProxyRotationAdapter:
    def next_proxy(self) -> str | None:
        return None


def _redact_sensitive_fields(payload: object) -> object:
    if isinstance(payload, dict):
        redacted: dict[object, object] = {}
        for key, value in payload.items():
            key_text = str(key).lower()
            if any(marker in key_text for marker in _SENSITIVE_PROXY_KEYS):
                redacted[key] = "***redacted***"
            else:
                redacted[key] = _redact_sensitive_fields(value)
        return redacted
    if isinstance(payload, list):
        return [_redact_sensitive_fields(value) for value in payload]
    return payload


@lru_cache
def get_proxy_rotation_adapter() -> ProxyRotationAdapter:
    settings = get_settings()
    raw = (settings.proxy_provider_config_json or "").strip()
    if not raw:
        logger.info("Proxy adapter disabled.", extra={"event": "proxy.adapter.disabled"})
        return NullProxyRotationAdapter()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Proxy adapter config is not valid JSON.", extra={"event": "proxy.adapter.invalid_config"})
        return NullProxyRotationAdapter()
    logger.info(
        "Proxy adapter configured.",
        extra={"event": "proxy.adapter.configured", "config": _redact_sensitive_fields(parsed)},
    )
    return NullProxyRotationAdapter()
