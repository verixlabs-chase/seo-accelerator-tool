from __future__ import annotations

from abc import ABC, abstractmethod
import time

from app.providers.circuit_breaker import CircuitBreaker
from app.providers.errors import ProviderError, classify_provider_error
from app.providers.execution_types import (
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderHealthSnapshot,
    QuotaSnapshot,
)
from app.providers.retry import RetryExhaustedError, RetryPolicy


class ProviderBase(ABC):
    def __init__(
        self,
        *,
        retry_policy: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._retry_policy = retry_policy or RetryPolicy()
        self._circuit_breaker = circuit_breaker or CircuitBreaker()

    def execute(self, request: ProviderExecutionRequest) -> ProviderExecutionResult:
        start = time.perf_counter()
        try:
            payload = self._retry_policy.execute(self._invoke_with_breaker(request))
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ProviderExecutionResult(
                success=True,
                latency_ms=latency_ms,
                quota_state=self.quota(),
                raw_payload=payload,
            )
        except RetryExhaustedError as exhausted:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ProviderExecutionResult(
                success=False,
                latency_ms=latency_ms,
                error=exhausted.last_error,
                quota_state=self.quota(),
            )
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.perf_counter() - start) * 1000)
            provider_error = exc if isinstance(exc, ProviderError) else classify_provider_error(exc)
            return ProviderExecutionResult(
                success=False,
                latency_ms=latency_ms,
                error=provider_error,
                quota_state=self.quota(),
            )

    def health(self) -> ProviderHealthSnapshot:
        snapshot = self._circuit_breaker.snapshot()
        return ProviderHealthSnapshot(
            state=snapshot.state,
            consecutive_failures=snapshot.consecutive_failures,
            open_until_epoch_seconds=snapshot.open_until_epoch_seconds,
        )

    def quota(self) -> QuotaSnapshot | None:
        return None

    def _invoke_with_breaker(self, request: ProviderExecutionRequest):
        def _inner() -> dict:
            self._circuit_breaker.before_call()
            try:
                payload = self._execute_impl(request)
                self._circuit_breaker.record_success()
                return payload
            except Exception:
                self._circuit_breaker.record_failure()
                raise

        return _inner

    @abstractmethod
    def _execute_impl(self, request: ProviderExecutionRequest) -> dict:
        raise NotImplementedError
