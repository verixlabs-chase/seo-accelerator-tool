from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4


_correlation_id_var: ContextVar[str | None] = ContextVar('correlation_id', default=None)


def get_correlation_id() -> str | None:
    return _correlation_id_var.get()


def set_correlation_id(correlation_id: str | None = None) -> str:
    value = (correlation_id or '').strip() or str(uuid4())
    _correlation_id_var.set(value)
    return value


def clear_correlation_id() -> None:
    _correlation_id_var.set(None)
