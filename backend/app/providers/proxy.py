from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings


class ProxyRotationAdapter(Protocol):
    def next_proxy(self) -> str | None:
        ...


class NullProxyRotationAdapter:
    def next_proxy(self) -> str | None:
        return None


@lru_cache
def get_proxy_rotation_adapter() -> ProxyRotationAdapter:
    settings = get_settings()
    raw = (settings.proxy_provider_config_json or "").strip()
    if not raw:
        return NullProxyRotationAdapter()
    return NullProxyRotationAdapter()
