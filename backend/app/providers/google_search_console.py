from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import quote

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
class SearchMetrics:
    query: str
    clicks: float
    impressions: float
    ctr: float
    position: float
    keys: list[str]


class SearchConsoleProviderAdapter(ProviderBase):
    provider_version = "google-search-console-v1"
    capability = "search_console_analytics"

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
        self._endpoint_base = "https://searchconsole.googleapis.com/webmasters/v3"

    def _execute_impl(self, request: ProviderExecutionRequest) -> dict:
        payload = request.payload
        organization_id = str(payload.get("organization_id", "")).strip()
        site_url = str(payload.get("site_url", "")).strip()
        start_date = str(payload.get("start_date", "")).strip()
        end_date = str(payload.get("end_date", "")).strip()
        if not organization_id or not site_url or not start_date or not end_date:
            raise ProviderBadRequestError(
                "organization_id, site_url, start_date, and end_date are required for Search Console calls."
            )

        credentials = resolve_provider_credentials(self._db, organization_id, "google")
        access_token = str(credentials.get("access_token", "")).strip()
        if not access_token:
            raise ProviderAuthError("Google OAuth access token missing for Search Console provider.")

        dimensions = payload.get("dimensions", ["query"])
        if not isinstance(dimensions, list):
            raise ProviderBadRequestError("dimensions must be a list.")
        row_limit = int(payload.get("row_limit", 1000))
        if row_limit <= 0:
            raise ProviderBadRequestError("row_limit must be greater than 0.")
        search_type = str(payload.get("search_type", "web")).strip() or "web"
        timeout_seconds = _resolve_timeout_seconds(payload, self._timeout_seconds)
        endpoint = f"{self._endpoint_base}/sites/{quote(site_url, safe='')}/searchAnalytics/query"

        request_body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": dimensions,
            "rowLimit": row_limit,
            "type": search_type,
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
            raise ProviderTimeoutError("Google Search Console request timed out.") from exc
        except httpx.ConnectError as exc:
            raise ProviderConnectionError("Google Search Console connection failed.") from exc
        except httpx.HTTPError as exc:
            raise ProviderDependencyError("Google Search Console dependency call failed.") from exc

        if response.status_code >= 400:
            _raise_for_google_error(response, service_name="Search Console")

        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderResponseFormatError("Google Search Console response is not valid JSON.") from exc
        if not isinstance(body, dict):
            raise ProviderResponseFormatError("Google Search Console response must be a JSON object.")

        rows = body.get("rows", [])
        if not isinstance(rows, list):
            raise ProviderResponseFormatError("Google Search Console rows must be a list.")

        metrics: list[SearchMetrics] = []
        for item in rows:
            if not isinstance(item, dict):
                raise ProviderResponseFormatError("Google Search Console row must be an object.")
            keys = item.get("keys", [])
            if not isinstance(keys, list):
                keys = []
            metrics.append(
                SearchMetrics(
                    query=str(keys[0]) if keys else "",
                    clicks=float(item.get("clicks", 0.0)),
                    impressions=float(item.get("impressions", 0.0)),
                    ctr=float(item.get("ctr", 0.0)),
                    position=float(item.get("position", 0.0)),
                    keys=[str(v) for v in keys],
                )
            )

        return {
            "dataset": "search_metrics",
            "rows": [asdict(m) for m in metrics],
            "row_count": len(metrics),
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
