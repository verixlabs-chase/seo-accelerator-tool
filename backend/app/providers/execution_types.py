from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.providers.errors import ProviderError


@dataclass(frozen=True)
class QuotaSnapshot:
    limit: int
    remaining: int
    reset_epoch_seconds: float | None = None


@dataclass(frozen=True)
class ProviderHealthSnapshot:
    state: str
    consecutive_failures: int
    open_until_epoch_seconds: float | None = None


@dataclass(frozen=True)
class ProviderExecutionRequest:
    operation: str
    payload: dict[str, Any]
    correlation_id: str | None = None


@dataclass(frozen=True)
class ProviderExecutionResult:
    success: bool
    latency_ms: int
    error: ProviderError | None = None
    quota_state: QuotaSnapshot | None = None
    raw_payload: dict[str, Any] | None = None
