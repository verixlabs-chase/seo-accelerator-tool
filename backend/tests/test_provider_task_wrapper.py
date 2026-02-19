from app.providers.errors import ProviderAuthError, ProviderTimeoutError
from app.providers.execution_types import ProviderExecutionRequest, ProviderExecutionResult
from app.providers.retry import RetryPolicy
from app.providers.base import ProviderBase
from app.tasks.provider_task import CeleryProviderTask


class _StubProvider(ProviderBase):
    def __init__(self, responses: list[ProviderExecutionResult]) -> None:
        super().__init__()
        self._responses = responses
        self.calls = 0

    def execute(self, request: ProviderExecutionRequest) -> ProviderExecutionResult:  # noqa: ARG002
        self.calls += 1
        index = min(self.calls - 1, len(self._responses) - 1)
        return self._responses[index]

    def _execute_impl(self, request: ProviderExecutionRequest) -> dict:  # noqa: ARG002
        return {}


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


def test_provider_task_continues_when_telemetry_callback_fails(monkeypatch) -> None:
    task = _ProviderTask()
    req = ProviderExecutionRequest(operation="snapshot", payload={"keyword": "seo-5"})
    provider = _StubProvider([ProviderExecutionResult(success=True, latency_ms=12, raw_payload={"ok": True})])

    from app.services.provider_telemetry_service import ProviderTelemetryService

    def _raise_metric(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("telemetry down")

    monkeypatch.setattr(ProviderTelemetryService, "record_execution_metric", _raise_metric)

    result = task.run_provider_call(provider=provider, request=req)
    assert result.success is True
    assert provider.calls == 1


def test_provider_task_idempotency_key_excludes_secret_fields() -> None:
    task = _ProviderTask()
    req = ProviderExecutionRequest(
        operation="snapshot",
        payload={
            "keyword": "safe",
            "api_key": "secret-value",
            "auth_token": "token-value",
            "credentials": {"password": "p"},
        },
    )
    key = task.build_idempotency_key(req)
    assert "secret-value" not in key
    assert "token-value" not in key
    assert "password" not in key


def test_provider_task_structured_logs_do_not_include_secret_values(caplog) -> None:
    task = _ProviderTask()
    secret = "super-secret-value"
    req = ProviderExecutionRequest(operation="snapshot", payload={"keyword": "seo", "api_key": secret})
    provider = _StubProvider([ProviderExecutionResult(success=True, latency_ms=12, raw_payload={"ok": True})])
    with caplog.at_level("INFO", logger="lsos.provider.task"):
        result = task.run_provider_call(provider=provider, request=req)
    assert result.success is True
    assert secret not in caplog.text
