from __future__ import annotations

from dataclasses import dataclass
import random
import time
from typing import Callable, TypeVar

from app.providers.errors import ProviderError, classify_provider_error


T = TypeVar("T")


@dataclass(frozen=True)
class RetryExhaustedError(Exception):
    last_error: ProviderError
    attempts: int

    def __str__(self) -> str:
        return f"Retry exhausted after {self.attempts} attempts: {self.last_error}"


class RetryPolicy:
    def __init__(
        self,
        *,
        max_attempts: int = 3,
        base_delay_seconds: float = 0.25,
        max_delay_seconds: float = 5.0,
        jitter_ratio: float = 0.1,
        sleep_fn: Callable[[float], None] = time.sleep,
        random_fn: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.max_attempts = max_attempts
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.jitter_ratio = jitter_ratio
        self.sleep_fn = sleep_fn
        self.random_fn = random_fn

    def delay_for_attempt(self, attempt_number: int) -> float:
        base = min(self.max_delay_seconds, self.base_delay_seconds * (2 ** (attempt_number - 1)))
        if self.jitter_ratio <= 0:
            return base
        jitter_multiplier = 1.0 + self.random_fn(-self.jitter_ratio, self.jitter_ratio)
        return max(0.0, min(self.max_delay_seconds, base * jitter_multiplier))

    def execute(
        self,
        operation: Callable[[], T],
        *,
        classify_error: Callable[[Exception], ProviderError] = classify_provider_error,
    ) -> T:
        attempt = 1
        while True:
            try:
                return operation()
            except Exception as exc:  # noqa: PERF203
                provider_error = classify_error(exc)
                if not provider_error.retryable:
                    raise provider_error
                if attempt >= self.max_attempts:
                    raise RetryExhaustedError(last_error=provider_error, attempts=attempt)
                self.sleep_fn(self.delay_for_attempt(attempt))
                attempt += 1
