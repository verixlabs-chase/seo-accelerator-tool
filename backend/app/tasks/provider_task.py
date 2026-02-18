from __future__ import annotations

import json
import logging
import time
from typing import Callable

from celery import Task

from app.providers.base import ProviderBase
from app.providers.errors import ProviderTimeoutError, classify_provider_error
from app.providers.execution_types import ProviderExecutionRequest, ProviderExecutionResult
from app.providers.retry import RetryExhaustedError, RetryPolicy


logger = logging.getLogger("lsos.provider.task")


class CeleryProviderTask(Task):
    abstract = True

    provider_name = "unknown"
    timeout_budget_seconds = 30.0
    retry_policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.25, max_delay_seconds=2.0, jitter_ratio=0.0)

    def __init__(self) -> None:
        super().__init__()
        self._idempotent_results: dict[str, ProviderExecutionResult] = {}

    def build_idempotency_key(self, request: ProviderExecutionRequest) -> str:
        normalized = json.dumps(
            {
                "operation": request.operation,
                "payload": request.payload,
            },
            sort_keys=True,
            default=str,
        )
        return f"{self.provider_name}:{normalized}"

    def run_provider_call(
        self,
        *,
        provider: ProviderBase,
        request: ProviderExecutionRequest,
        dead_letter_hook: Callable[[dict], None] | None = None,
    ) -> ProviderExecutionResult:
        idempotency_key = self.build_idempotency_key(request)
        if idempotency_key in self._idempotent_results:
            result = self._idempotent_results[idempotency_key]
            self._log_event("provider.idempotent_hit", request=request, idempotency_key=idempotency_key, result=result)
            return result

        started_at = time.perf_counter()
        try:
            result = self.retry_policy.execute(
                lambda: self._invoke_with_timeout(provider=provider, request=request, started_at=started_at),
                classify_error=classify_provider_error,
            )
            self._idempotent_results[idempotency_key] = result
            self._log_event("provider.execution_finished", request=request, idempotency_key=idempotency_key, result=result)
            return result
        except RetryExhaustedError as exhausted:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            failed_result = ProviderExecutionResult(
                success=False,
                latency_ms=latency_ms,
                error=exhausted.last_error,
            )
            self._idempotent_results[idempotency_key] = failed_result
            self._log_event("provider.execution_failed", request=request, idempotency_key=idempotency_key, result=failed_result)
            if dead_letter_hook is not None:
                dead_letter_hook(self._dead_letter_payload(request=request, idempotency_key=idempotency_key, result=failed_result))
            return failed_result
        except Exception as exc:  # noqa: BLE001
            provider_error = classify_provider_error(exc)
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            failed_result = ProviderExecutionResult(
                success=False,
                latency_ms=latency_ms,
                error=provider_error,
            )
            self._idempotent_results[idempotency_key] = failed_result
            self._log_event("provider.execution_failed", request=request, idempotency_key=idempotency_key, result=failed_result)
            if dead_letter_hook is not None and provider_error.retryable:
                dead_letter_hook(self._dead_letter_payload(request=request, idempotency_key=idempotency_key, result=failed_result))
            return failed_result

    def _invoke_with_timeout(self, *, provider: ProviderBase, request: ProviderExecutionRequest, started_at: float) -> ProviderExecutionResult:
        elapsed_seconds = time.perf_counter() - started_at
        if elapsed_seconds > self.timeout_budget_seconds:
            raise ProviderTimeoutError("Task timeout budget exceeded before provider call.")
        result = provider.execute(request)
        elapsed_seconds = time.perf_counter() - started_at
        if elapsed_seconds > self.timeout_budget_seconds:
            raise ProviderTimeoutError("Task timeout budget exceeded after provider call.")
        if not result.success and result.error is not None:
            raise result.error
        return result

    def _dead_letter_payload(
        self,
        *,
        request: ProviderExecutionRequest,
        idempotency_key: str,
        result: ProviderExecutionResult,
    ) -> dict:
        error = result.error
        return {
            "task_name": self.name,
            "provider_name": self.provider_name,
            "operation": request.operation,
            "idempotency_key": idempotency_key,
            "correlation_id": request.correlation_id,
            "reason_code": error.reason_code if error is not None else "unknown",
            "error_code": error.error_code if error is not None else "unknown",
            "error_message": str(error) if error is not None else "unknown",
            "retryable": error.retryable if error is not None else False,
            "latency_ms": result.latency_ms,
        }

    def _log_event(
        self,
        event: str,
        *,
        request: ProviderExecutionRequest,
        idempotency_key: str,
        result: ProviderExecutionResult,
    ) -> None:
        logger.info(
            json.dumps(
                {
                    "event": event,
                    "task_name": self.name,
                    "provider_name": self.provider_name,
                    "operation": request.operation,
                    "correlation_id": request.correlation_id,
                    "idempotency_key": idempotency_key,
                    "success": result.success,
                    "latency_ms": result.latency_ms,
                    "reason_code": result.error.reason_code if result.error is not None else None,
                }
            )
        )
