from app.providers.errors import ProviderAuthError, ProviderTimeoutError
from app.providers.execution_types import ProviderExecutionRequest, ProviderExecutionResult
from app.providers.retry import RetryPolicy
from app.tasks.provider_task import CeleryProviderTask


class _StubProvider:
    def __init__(self, responses: list[ProviderExecutionResult]) -> None:
        self._responses = responses
        self.calls = 0

    def execute(self, request: ProviderExecutionRequest) -> ProviderExecutionResult:  # noqa: ARG002
        self.calls += 1
        index = min(self.calls - 1, len(self._responses) - 1)
        return self._responses[index]


class _ProviderTask(CeleryProviderTask):
    name = "tests.provider.task"
    provider_name = "test_provider"
    timeout_budget_seconds = 10.0
    retry_policy = RetryPolicy(max_attempts=2, jitter_ratio=0.0, sleep_fn=lambda _d: None)


def test_provider_task_idempotency_reuses_first_result() -> None:
    task = _ProviderTask()
    req = ProviderExecutionRequest(operation="snapshot", payload={"keyword": "seo"})
    provider = _StubProvider([ProviderExecutionResult(success=True, latency_ms=12, raw_payload={"ok": True})])

    first = task.run_provider_call(provider=provider, request=req)
    second = task.run_provider_call(provider=provider, request=req)

    assert first.success is True
    assert second.success is True
    assert provider.calls == 1


def test_provider_task_retries_retryable_then_succeeds() -> None:
    task = _ProviderTask()
    req = ProviderExecutionRequest(operation="snapshot", payload={"keyword": "seo-2"})
    provider = _StubProvider(
        [
            ProviderExecutionResult(success=False, latency_ms=3, error=ProviderTimeoutError("slow provider")),
            ProviderExecutionResult(success=True, latency_ms=4, raw_payload={"position": 1}),
        ]
    )
    result = task.run_provider_call(provider=provider, request=req)
    assert result.success is True
    assert provider.calls == 2


def test_provider_task_non_retryable_error_propagates_without_dead_letter() -> None:
    task = _ProviderTask()
    req = ProviderExecutionRequest(operation="snapshot", payload={"keyword": "seo-3"})
    provider = _StubProvider(
        [
            ProviderExecutionResult(success=False, latency_ms=5, error=ProviderAuthError("invalid token")),
        ]
    )
    dead_letters: list[dict] = []
    result = task.run_provider_call(provider=provider, request=req, dead_letter_hook=lambda payload: dead_letters.append(payload))
    assert result.success is False
    assert result.error is not None
    assert result.error.reason_code == "auth_failed"
    assert dead_letters == []


def test_provider_task_dead_letter_on_retry_exhaustion() -> None:
    task = _ProviderTask()
    req = ProviderExecutionRequest(operation="snapshot", payload={"keyword": "seo-4"})
    provider = _StubProvider(
        [
            ProviderExecutionResult(success=False, latency_ms=5, error=ProviderTimeoutError("slow-1")),
            ProviderExecutionResult(success=False, latency_ms=5, error=ProviderTimeoutError("slow-2")),
        ]
    )
    dead_letters: list[dict] = []
    result = task.run_provider_call(provider=provider, request=req, dead_letter_hook=lambda payload: dead_letters.append(payload))
    assert result.success is False
    assert result.error is not None
    assert result.error.reason_code == "timeout"
    assert len(dead_letters) == 1
    assert dead_letters[0]["reason_code"] == "timeout"
