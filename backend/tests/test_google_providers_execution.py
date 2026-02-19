from __future__ import annotations

import base64
from typing import Any
from typing import Literal

import pytest

from app.models.provider_metric import ProviderExecutionMetric
from app.providers.circuit_breaker import CircuitBreaker
from app.providers.execution_types import ProviderExecutionRequest
from app.providers.google_analytics import GoogleAnalyticsProviderAdapter
from app.providers.google_places import GooglePlacesProviderAdapter
from app.providers.google_search_console import SearchConsoleProviderAdapter
from app.providers.retry import RetryPolicy
from app.tasks.provider_task import CeleryProviderTask


MASTER_KEY_B64 = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii")


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    def __init__(self, actions: list[Any], calls: list[dict[str, Any]]) -> None:
        self._actions = actions
        self._calls = calls

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> Literal[False]:
        return False

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str], timeout: float):  # noqa: A002
        self._calls.append({"method": "POST", "url": url, "json": json, "headers": headers, "timeout": timeout})
        action = self._actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action

    def get(self, url: str, headers: dict[str, str], timeout: float):
        self._calls.append({"method": "GET", "url": url, "headers": headers, "timeout": timeout})
        action = self._actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


@pytest.fixture(autouse=True)
def _set_env(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)


def _patch_http_client(monkeypatch, module_name: str, actions: list[Any], calls: list[dict[str, Any]]) -> None:
    monkeypatch.setattr(
        f"{module_name}.httpx.Client",
        lambda: _FakeClient(actions=actions, calls=calls),
    )


def _patch_credentials(monkeypatch, module_name: str) -> None:
    monkeypatch.setattr(
        f"{module_name}.resolve_provider_credentials",
        lambda _db, _org, _provider: {
            "access_token": "access-token-value",
            "refresh_token": "refresh-token-value",
            "expires_at": 4102444800,
        },
    )


def test_search_console_adapter_normalizes_rows(db_session, monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    actions = [
        _FakeResponse(
            status_code=200,
            payload={
                "rows": [
                    {"keys": ["best seo austin"], "clicks": 11, "impressions": 100, "ctr": 0.11, "position": 5.2}
                ]
            },
        )
    ]
    _patch_credentials(monkeypatch, "app.providers.google_search_console")
    _patch_http_client(monkeypatch, "app.providers.google_search_console", actions, calls)

    provider = SearchConsoleProviderAdapter(
        db=db_session,
        retry_policy=RetryPolicy(max_attempts=1, jitter_ratio=0.0),
    )
    result = provider.execute(
        ProviderExecutionRequest(
            operation="search_console_query",
            payload={
                "organization_id": "org-1",
                "site_url": "sc-domain:example.com",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
            },
        )
    )

    assert result.success is True
    assert result.raw_payload is not None
    assert result.raw_payload["dataset"] == "search_metrics"
    assert result.raw_payload["rows"][0]["query"] == "best seo austin"
    assert calls[0]["method"] == "POST"


def test_google_analytics_adapter_normalizes_dataset_and_enforces_timeout_budget(db_session, monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    actions = [
        _FakeResponse(
            status_code=200,
            payload={
                "dimensionHeaders": [{"name": "date"}],
                "metricHeaders": [{"name": "activeUsers"}],
                "rows": [{"dimensionValues": [{"value": "20260219"}], "metricValues": [{"value": "27"}]}],
            },
        )
    ]
    _patch_credentials(monkeypatch, "app.providers.google_analytics")
    _patch_http_client(monkeypatch, "app.providers.google_analytics", actions, calls)

    provider = GoogleAnalyticsProviderAdapter(
        db=db_session,
        timeout_seconds=5.0,
        retry_policy=RetryPolicy(max_attempts=1, jitter_ratio=0.0),
    )
    result = provider.execute(
        ProviderExecutionRequest(
            operation="ga4_run_report",
            payload={
                "organization_id": "org-1",
                "property_id": "12345",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "dimensions": ["date"],
                "metrics": ["activeUsers"],
                "timeout_budget_ms": 250,
            },
        )
    )

    assert result.success is True
    assert result.raw_payload is not None
    assert result.raw_payload["dataset"] == "analytics_dataset"
    row = result.raw_payload["rows"][0]
    assert row["dimension_values"]["date"] == "20260219"
    assert row["metric_values"]["activeUsers"] == 27.0
    assert calls[0]["timeout"] == 0.25


def test_google_places_adapter_normalizes_place_details(db_session, monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    actions = [
        _FakeResponse(
            status_code=200,
            payload={
                "id": "places/abc123",
                "displayName": {"text": "TopDog Local"},
                "formattedAddress": "123 Main St, Austin, TX",
                "websiteUri": "https://example.com",
                "nationalPhoneNumber": "+1 512-555-1000",
                "businessStatus": "OPERATIONAL",
            },
        )
    ]
    _patch_credentials(monkeypatch, "app.providers.google_places")
    _patch_http_client(monkeypatch, "app.providers.google_places", actions, calls)

    provider = GooglePlacesProviderAdapter(
        db=db_session,
        retry_policy=RetryPolicy(max_attempts=1, jitter_ratio=0.0),
    )
    result = provider.execute(
        ProviderExecutionRequest(
            operation="place_details",
            payload={"organization_id": "org-1", "place_id": "ChIJ123"},
        )
    )

    assert result.success is True
    assert result.raw_payload is not None
    assert result.raw_payload["dataset"] == "place_details"
    assert result.raw_payload["details"]["name"] == "TopDog Local"
    assert calls[0]["method"] == "GET"


def test_search_console_adapter_retries_rate_limited_response(db_session, monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    actions = [
        _FakeResponse(
            status_code=429,
            payload={"error": {"status": "RESOURCE_EXHAUSTED", "message": "Too many requests"}},
        ),
        _FakeResponse(
            status_code=200,
            payload={"rows": [{"keys": ["q"], "clicks": 1, "impressions": 10, "ctr": 0.1, "position": 2.0}]},
        ),
    ]
    _patch_credentials(monkeypatch, "app.providers.google_search_console")
    _patch_http_client(monkeypatch, "app.providers.google_search_console", actions, calls)

    provider = SearchConsoleProviderAdapter(
        db=db_session,
        retry_policy=RetryPolicy(max_attempts=2, jitter_ratio=0.0, sleep_fn=lambda _d: None),
    )
    result = provider.execute(
        ProviderExecutionRequest(
            operation="search_console_query",
            payload={
                "organization_id": "org-1",
                "site_url": "sc-domain:example.com",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
            },
        )
    )

    assert result.success is True
    assert len(calls) == 2


def test_google_places_adapter_circuit_breaker_opens_after_dependency_failures(db_session, monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    actions = [
        _FakeResponse(status_code=503, payload={"error": {"status": "UNAVAILABLE"}}),
    ]
    _patch_credentials(monkeypatch, "app.providers.google_places")
    _patch_http_client(monkeypatch, "app.providers.google_places", actions, calls)

    provider = GooglePlacesProviderAdapter(
        db=db_session,
        retry_policy=RetryPolicy(max_attempts=1, jitter_ratio=0.0),
        circuit_breaker=CircuitBreaker(failure_threshold=1, reset_timeout=60.0),
    )
    request = ProviderExecutionRequest(
        operation="place_details",
        payload={"organization_id": "org-1", "place_id": "ChIJ123"},
    )
    first = provider.execute(request)
    second = provider.execute(request)

    assert first.success is False
    assert first.error is not None
    assert first.error.reason_code == "dependency_unavailable"
    assert second.success is False
    assert second.error is not None
    assert second.error.reason_code == "circuit_open"
    assert len(calls) == 1


class _GoogleProviderTask(CeleryProviderTask):
    name = "tests.google.provider.task"
    provider_name = "google_search_console"
    capability = "search_console_analytics"
    timeout_budget_seconds = 5.0
    retry_policy = RetryPolicy(max_attempts=1, jitter_ratio=0.0, sleep_fn=lambda _d: None)


def test_google_provider_execution_persists_telemetry(db_session, monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    actions = [
        _FakeResponse(
            status_code=200,
            payload={"rows": [{"keys": ["q"], "clicks": 1, "impressions": 10, "ctr": 0.1, "position": 3.0}]},
        )
    ]
    _patch_credentials(monkeypatch, "app.providers.google_search_console")
    _patch_http_client(monkeypatch, "app.providers.google_search_console", actions, calls)

    provider = SearchConsoleProviderAdapter(
        db=db_session,
        retry_policy=RetryPolicy(max_attempts=1, jitter_ratio=0.0),
    )
    task = _GoogleProviderTask()
    request = ProviderExecutionRequest(
        operation="search_console_query",
        payload={
            "tenant_id": "tenant-telemetry",
            "organization_id": "org-1",
            "site_url": "sc-domain:example.com",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        },
        correlation_id="corr-123",
    )
    result = task.run_provider_call(provider=provider, request=request)

    assert result.success is True
    metric = db_session.query(ProviderExecutionMetric).filter(ProviderExecutionMetric.provider_name == "google_search_console").first()
    assert metric is not None
    assert metric.outcome == "success"
    assert metric.reason_code is None
