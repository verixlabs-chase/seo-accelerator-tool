from __future__ import annotations

from dataclasses import dataclass
import time

from app.providers.errors import ProviderCircuitOpenError


@dataclass(frozen=True)
class CircuitBreakerSnapshot:
    state: str
    consecutive_failures: int
    open_until_epoch_seconds: float | None


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._state = "closed"
        self._consecutive_failures = 0
        self._open_until_epoch_seconds: float | None = None
        self._half_open_probe_in_flight = False

    def snapshot(self) -> CircuitBreakerSnapshot:
        return CircuitBreakerSnapshot(
            state=self.state(),
            consecutive_failures=self._consecutive_failures,
            open_until_epoch_seconds=self._open_until_epoch_seconds,
        )

    def state(self, *, now: float | None = None) -> str:
        now_value = time.time() if now is None else now
        if self._state == "open" and self._open_until_epoch_seconds is not None and now_value >= self._open_until_epoch_seconds:
            self._state = "half_open"
            self._half_open_probe_in_flight = False
        return self._state

    def before_call(self, *, now: float | None = None) -> None:
        state = self.state(now=now)
        if state == "open":
            raise ProviderCircuitOpenError()
        if state == "half_open":
            if self._half_open_probe_in_flight:
                raise ProviderCircuitOpenError("Provider circuit half-open probe already in progress.")
            self._half_open_probe_in_flight = True

    def record_success(self) -> None:
        self._state = "closed"
        self._consecutive_failures = 0
        self._open_until_epoch_seconds = None
        self._half_open_probe_in_flight = False

    def record_failure(self, *, now: float | None = None) -> None:
        now_value = time.time() if now is None else now
        if self.state(now=now_value) == "half_open":
            self._state = "open"
            self._open_until_epoch_seconds = now_value + self.reset_timeout
            self._half_open_probe_in_flight = False
            return

        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._state = "open"
            self._open_until_epoch_seconds = now_value + self.reset_timeout
            self._half_open_probe_in_flight = False
