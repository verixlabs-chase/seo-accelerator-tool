from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.providers.base import ProviderBase
from app.providers.errors import (
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderConnectionError,
    ProviderDependencyError,
    ProviderQuotaExceededError,
    ProviderRateLimitError,
    ProviderResponseFormatError,
    ProviderTimeoutError,
)
from app.providers.execution_types import ProviderExecutionRequest
from app.services.provider_credentials_service import resolve_provider_credentials


@dataclass(frozen=True)
class AnalyticsDataset:
    dimension_values: dict[str, str]
    metric_values: dict[str, float]


class GoogleAnalyticsProviderAdapter(ProviderBase):
    provider_version = "google-analytics-v1"
    capability = "analytics_report"

    def __init__(
        self,
        *,
        db: Session,
        timeout_seconds: float | None = None,
        retry_policy=None,
        circuit_breaker=None,
    ) -> None:
        super().__init__(retry_policy=retry_policy, circuit_breaker=circuit_breaker)
        self._db = db
        settings = get_settings()
        self._timeout_seconds = float(timeout_seconds or settings.google_oauth_http_timeout_seconds)
        self._endpoint_base = "https://analyticsdata.googleapis.com/v1beta"

    def _execute_impl(self, request: ProviderExecutionRequest) -> dict:
        payload = request.payload
        organization_id = str(payload.get("organization_id", "")).strip()
        property_id = str(payload.get("property_id", "")).strip()
        start_date = str(payload.get("start_date", "")).strip()
        end_date = str(payload.get("end_date", "")).strip()
        dimensions = payload.get("dimensions", [])
        metrics = payload.get("metrics", [])
        if not organization_id or not property_id or not start_date or not end_date:
            raise ProviderBadRequestError(
                "organization_id, property_id, start_date, and end_date are required for GA4 report calls."
            )
        if not isinstance(dimensions, list) or not isinstance(metrics, list) or not metrics:
            raise ProviderBadRequestError("dimensions and metrics must be lists, and metrics cannot be empty.")

        credentials = resolve_provider_credentials(self._db, organization_id, "google")
        access_token = str(credentials.get("access_token", "")).strip()
        if not access_token:
            raise ProviderAuthError("Google OAuth access token missing for Google Analytics provider.")

        timeout_seconds = _resolve_timeout_seconds(payload, self._timeout_seconds)
        endpoint = f"{self._endpoint_base}/properties/{property_id}:runReport"
        request_body = {
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": str(v)} for v in dimensions],
            "metrics": [{"name": str(v)} for v in metrics],
            "limit": str(int(payload.get("limit", 1000))),
        }
        try:
            with httpx.Client() as client:
                response = client.post(
                    endpoint,
                    json=request_body,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=timeout_seconds,
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Google Analytics request timed out.") from exc
        except httpx.ConnectError as exc:
            raise ProviderConnectionError("Google Analytics connection failed.") from exc
        except httpx.HTTPError as exc:
            raise ProviderDependencyError("Google Analytics dependency call failed.") from exc

        if response.status_code >= 400:
            _raise_for_google_error(response, service_name="Analytics")

        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderResponseFormatError("Google Analytics response is not valid JSON.") from exc
        if not isinstance(body, dict):
            raise ProviderResponseFormatError("Google Analytics response must be a JSON object.")

        dimension_headers = _extract_header_names(body.get("dimensionHeaders"))
        metric_headers = _extract_header_names(body.get("metricHeaders"))
        rows = body.get("rows", [])
        if not isinstance(rows, list):
            raise ProviderResponseFormatError("Google Analytics rows must be a list.")

        dataset: list[AnalyticsDataset] = []
        for item in rows:
            if not isinstance(item, dict):
                raise ProviderResponseFormatError("Google Analytics row must be an object.")
            dimension_values = _extract_value_map(item.get("dimensionValues"), dimension_headers)
            metric_values = _extract_metric_map(item.get("metricValues"), metric_headers)
            dataset.append(AnalyticsDataset(dimension_values=dimension_values, metric_values=metric_values))

        return {
            "dataset": "analytics_dataset",
            "rows": [asdict(row) for row in dataset],
            "row_count": len(dataset),
        }


def _resolve_timeout_seconds(payload: dict[str, Any], default_timeout_seconds: float) -> float:
    timeout_budget_ms = payload.get("timeout_budget_ms")
    if timeout_budget_ms is None:
        return default_timeout_seconds
    try:
        timeout_budget_seconds = float(timeout_budget_ms) / 1000.0
    except (TypeError, ValueError) as exc:
        raise ProviderBadRequestError("timeout_budget_ms must be numeric.") from exc
    if timeout_budget_seconds <= 0:
        raise ProviderBadRequestError("timeout_budget_ms must be greater than 0.")
    return min(default_timeout_seconds, timeout_budget_seconds)


def _extract_header_names(raw_headers: Any) -> list[str]:
    if not isinstance(raw_headers, list):
        return []
    names: list[str] = []
    for item in raw_headers:
        if isinstance(item, dict):
            names.append(str(item.get("name", "")))
    return names


def _extract_value_map(raw_values: Any, headers: list[str]) -> dict[str, str]:
    if not isinstance(raw_values, list):
        return {}
    mapped: dict[str, str] = {}
    for idx, item in enumerate(raw_values):
        if not isinstance(item, dict):
            continue
        name = headers[idx] if idx < len(headers) else f"dimension_{idx}"
        mapped[name] = str(item.get("value", ""))
    return mapped


def _extract_metric_map(raw_values: Any, headers: list[str]) -> dict[str, float]:
    if not isinstance(raw_values, list):
        return {}
    mapped: dict[str, float] = {}
    for idx, item in enumerate(raw_values):
        if not isinstance(item, dict):
            continue
        name = headers[idx] if idx < len(headers) else f"metric_{idx}"
        value_raw = item.get("value", "0")
        try:
            mapped[name] = float(value_raw)
        except (TypeError, ValueError):
            mapped[name] = 0.0
    return mapped


def _raise_for_google_error(response: httpx.Response, *, service_name: str) -> None:
    status = response.status_code
    body = _safe_json(response)
    reason = _extract_google_reason(body)
    message = f"Google {service_name} request failed with status {status}."
    if status in {401, 403}:
        if "quota" in reason:
            raise ProviderQuotaExceededError(message, upstream_payload=body)
        raise ProviderAuthError(message, upstream_payload=body)
    if status == 429:
        raise ProviderRateLimitError(message, upstream_payload=body)
    if status in {408, 504}:
        raise ProviderTimeoutError(message, upstream_payload=body)
    if 400 <= status < 500:
        raise ProviderBadRequestError(message, upstream_payload=body)
    if status >= 500:
        raise ProviderDependencyError(message, upstream_payload=body)
    raise ProviderDependencyError(message, upstream_payload=body)


def _safe_json(response: httpx.Response) -> dict[str, Any] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _extract_google_reason(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        details = error.get("errors")
        if isinstance(details, list) and details:
            first = details[0]
            if isinstance(first, dict):
                return str(first.get("reason", "")).lower()
        status_text = error.get("status")
        if isinstance(status_text, str):
            return status_text.lower()
    return ""
