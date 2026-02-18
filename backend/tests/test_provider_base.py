from app.providers.base import ProviderBase
from app.providers.errors import ProviderAuthError
from app.providers.execution_types import ProviderExecutionRequest, QuotaSnapshot
from app.providers.retry import RetryPolicy


class _QuotaProvider(ProviderBase):
    def __init__(self) -> None:
        super().__init__(retry_policy=RetryPolicy(max_attempts=1, jitter_ratio=0.0))

    def quota(self) -> QuotaSnapshot | None:
        return QuotaSnapshot(limit=100, remaining=99)

    def _execute_impl(self, request: ProviderExecutionRequest) -> dict:
        return {"echo": request.payload}


class _FailingProvider(ProviderBase):
    def __init__(self) -> None:
        super().__init__(retry_policy=RetryPolicy(max_attempts=1, jitter_ratio=0.0))

    def _execute_impl(self, request: ProviderExecutionRequest) -> dict:  # noqa: ARG002
        raise ProviderAuthError("bad auth")


def test_provider_base_execute_success() -> None:
    provider = _QuotaProvider()
    result = provider.execute(ProviderExecutionRequest(operation="test", payload={"x": 1}))
    assert result.success is True
    assert result.raw_payload == {"echo": {"x": 1}}
    assert result.quota_state is not None
    assert result.quota_state.remaining == 99


def test_provider_base_execute_failure_returns_canonical_error() -> None:
    provider = _FailingProvider()
    result = provider.execute(ProviderExecutionRequest(operation="test", payload={}))
    assert result.success is False
    assert result.error is not None
    assert result.error.reason_code == "auth_failed"
    assert result.error.retryable is False
