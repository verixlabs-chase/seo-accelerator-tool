from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from app.core.correlation import get_correlation_id


logger = logging.getLogger('lsos.provider.client')


class ProviderCallError(RuntimeError):
    def __init__(self, message: str, *, provider_name: str, operation: str, attempts: int, correlation_id: str | None = None) -> None:
        super().__init__(message)
        self.provider_name = provider_name
        self.operation = operation
        self.attempts = attempts
        self.correlation_id = correlation_id


def call_provider(
    provider_name: str,
    operation: str,
    fn: Callable[[], Any],
    timeout: int = 10,
    retries: int = 3,
) -> Any:
    attempts = max(1, int(retries))
    correlation_id = get_correlation_id()
    last_exc: Exception | None = None

    for attempt in range(1, attempts + 1):
        started_at = time.perf_counter()
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fn)
                result = future.result(timeout=max(1, int(timeout)))
            logger.info(
                'provider_call_success',
                extra={
                    'provider_name': provider_name,
                    'operation': operation,
                    'attempt': attempt,
                    'duration_ms': int((time.perf_counter() - started_at) * 1000),
                    'correlation_id': correlation_id,
                },
            )
            return result
        except FutureTimeoutError as exc:
            last_exc = TimeoutError(f'Provider call timed out after {timeout}s')
            logger.warning(
                'provider_call_timeout',
                extra={
                    'provider_name': provider_name,
                    'operation': operation,
                    'attempt': attempt,
                    'retries': attempts,
                    'correlation_id': correlation_id,
                },
                exc_info=exc,
            )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                'provider_call_failure',
                extra={
                    'provider_name': provider_name,
                    'operation': operation,
                    'attempt': attempt,
                    'retries': attempts,
                    'correlation_id': correlation_id,
                },
                exc_info=exc,
            )
        if attempt < attempts:
            backoff_seconds = min(2.0, 0.25 * (2 ** (attempt - 1)))
            time.sleep(backoff_seconds)

    raise ProviderCallError(
        f'Provider call failed: {provider_name}.{operation}',
        provider_name=provider_name,
        operation=operation,
        attempts=attempts,
        correlation_id=correlation_id,
    ) from last_exc
