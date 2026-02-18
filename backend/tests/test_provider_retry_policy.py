import pytest

from app.providers.errors import ProviderAuthError, ProviderTimeoutError
from app.providers.retry import RetryExhaustedError, RetryPolicy


def test_retry_policy_retries_until_success() -> None:
    calls = {"count": 0}
    sleeps: list[float] = []
    policy = RetryPolicy(
        max_attempts=3,
        base_delay_seconds=0.5,
        max_delay_seconds=5.0,
        jitter_ratio=0.0,
        sleep_fn=lambda d: sleeps.append(d),
    )

    def _op() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            raise ProviderTimeoutError()
        return "ok"

    assert policy.execute(_op) == "ok"
    assert calls["count"] == 3
    assert sleeps == [0.5, 1.0]


def test_retry_policy_raises_exhausted_for_retryable_error() -> None:
    policy = RetryPolicy(max_attempts=2, jitter_ratio=0.0, sleep_fn=lambda _d: None)
    with pytest.raises(RetryExhaustedError) as exc:
        policy.execute(lambda: (_ for _ in ()).throw(ProviderTimeoutError()))
    assert exc.value.attempts == 2
    assert exc.value.last_error.reason_code == "timeout"


def test_retry_policy_propagates_non_retryable_without_sleep() -> None:
    slept = {"called": False}
    policy = RetryPolicy(max_attempts=5, sleep_fn=lambda _d: slept.__setitem__("called", True))
    with pytest.raises(ProviderAuthError):
        policy.execute(lambda: (_ for _ in ()).throw(ProviderAuthError("bad token")))
    assert slept["called"] is False
