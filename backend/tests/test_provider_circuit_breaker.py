import pytest

from app.providers.circuit_breaker import CircuitBreaker
from app.providers.errors import ProviderCircuitOpenError


def test_circuit_breaker_opens_after_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=5.0)
    breaker.before_call(now=100.0)
    breaker.record_failure(now=100.0)
    breaker.before_call(now=100.1)
    breaker.record_failure(now=100.1)
    with pytest.raises(ProviderCircuitOpenError):
        breaker.before_call(now=101.0)


def test_circuit_breaker_transitions_to_half_open_and_closes_on_success() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=3.0)
    breaker.before_call(now=10.0)
    breaker.record_failure(now=10.0)
    with pytest.raises(ProviderCircuitOpenError):
        breaker.before_call(now=11.0)
    breaker.before_call(now=13.1)
    breaker.record_success()
    breaker.before_call(now=13.2)


def test_circuit_breaker_half_open_failed_probe_reopens() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=2.0)
    breaker.before_call(now=20.0)
    breaker.record_failure(now=20.0)
    breaker.before_call(now=22.1)
    breaker.record_failure(now=22.1)
    with pytest.raises(ProviderCircuitOpenError):
        breaker.before_call(now=22.2)
