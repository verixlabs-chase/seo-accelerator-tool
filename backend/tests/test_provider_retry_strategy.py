from __future__ import annotations

from app.providers.errors import ProviderTimeoutError
from app.providers.retry import NoSleepRetryStrategy, RealRetryStrategy, RetryPolicy, RetryExhaustedError


def test_no_sleep_strategy_always_zero_delay() -> None:
    strategy = NoSleepRetryStrategy()
    assert strategy.compute_delay(1) == 0.0
    assert strategy.compute_delay(3) == 0.0


def test_real_strategy_deterministic_delay() -> None:
    strategy = RealRetryStrategy(base_delay_seconds=0.25, max_delay_seconds=5.0, jitter_ratio=0.0)
    assert strategy.compute_delay(1) == 0.25
    assert strategy.compute_delay(2) == 0.5


def test_retry_policy_with_no_sleep_strategy_retries_without_waiting() -> None:
    attempts = {'count': 0}
    policy = RetryPolicy(max_attempts=2, base_delay_seconds=1.0, strategy=NoSleepRetryStrategy())

    def _op() -> int:
        attempts['count'] += 1
        if attempts['count'] == 1:
            raise ProviderTimeoutError('retry me')
        return 7

    assert policy.execute(_op) == 7
    assert attempts['count'] == 2


def test_retry_policy_exhausted_raises() -> None:
    attempts = {'count': 0}
    policy = RetryPolicy(max_attempts=2, strategy=NoSleepRetryStrategy())

    def _op() -> int:
        attempts['count'] += 1
        raise ProviderTimeoutError('retry me')

    try:
        policy.execute(_op)
    except RetryExhaustedError as exc:
        assert exc.attempts == 2
    else:
        raise AssertionError('Expected RetryExhaustedError')
