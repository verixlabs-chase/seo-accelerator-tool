from __future__ import annotations

import time
from functools import lru_cache
from typing import Protocol


class EmailAdapter(Protocol):
    def send_email(self, recipient: str, subject: str, body: str) -> dict:
        ...


class SyntheticEmailAdapter:
    def __init__(self, *, retry_attempts: int = 3, circuit_breaker_threshold: int = 5, circuit_breaker_cooldown_seconds: int = 60) -> None:
        self.retry_attempts = retry_attempts
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_cooldown_seconds = circuit_breaker_cooldown_seconds
        self._failure_count = 0
        self._open_until = 0.0

    def _circuit_open(self) -> bool:
        return time.time() < self._open_until

    def _record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self.circuit_breaker_threshold:
            self._open_until = time.time() + self.circuit_breaker_cooldown_seconds
            self._failure_count = 0

    def _record_success(self) -> None:
        self._failure_count = 0
        self._open_until = 0.0

    def send_email(self, recipient: str, subject: str, body: str) -> dict:  # noqa: ARG002
        if self._circuit_open():
            return {"status": "deferred", "reason": "circuit_open"}
        attempt = 0
        while attempt < self.retry_attempts:
            attempt += 1
            try:
                self._record_success()
                return {"status": "sent", "recipient": recipient}
            except Exception:
                self._record_failure()
                if attempt < self.retry_attempts:
                    time.sleep(0.25 * (2 ** (attempt - 1)))
        return {"status": "failed", "recipient": recipient}


@lru_cache
def get_email_adapter() -> EmailAdapter:
    return SyntheticEmailAdapter()
