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
    ProviderContractReviewError,
    ProviderDependencyError,
    ProviderQuotaExceededError,
    ProviderRateLimitError,
    ProviderResponseFormatError,
    ProviderTimeoutError,
)
from app.providers.execution_types import ProviderExecutionRequest
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    resolve_provider_credentials,
)
from app.services import standards_source_service


@dataclass(frozen=True)
class SearchMetrics:
    query: str
    clicks: float
    impressions: float
    ctr: float
    position: float
    keys: list[str]


@dataclass(frozen=True)
class UrlInspectionRecord:
    inspection_url: str
    site_url: str
    verdict: str
    coverage_state: str | None
    robots_txt_state: str | None
    indexing_state: str | None
    page_fetch_state: str | None
    google_canonical: str | None
    user_canonical: str | None
    crawled_as: str | None
    last_crawl_time: str | None
    sitemap_urls: list[str]
    referring_urls: list[str]


@dataclass(frozen=True)
class SitemapRecord:
    site_url: str
    sitemap_url: str
    sitemap_type: str | None
    is_pending: bool
    is_sitemaps_index: bool
    warnings: int
    errors: int
    submitted_url_count: int
    contents: list[dict[str, Any]]
    last_submitted_at: str | None
    last_downloaded_at: str | None


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
        try:
            standards_source_service.assert_provider_contract_ready(
                self._db,
                "google_search_console",
            )
        except standards_source_service.StandardsContractBlockedError as exc:
            raise ProviderContractReviewError(str(exc)) from exc
        payload = request.payload
        organization_id = str(payload.get("organization_id", "")).strip()
        site_url = str(payload.get("site_url", "")).strip()
        start_date = str(payload.get("start_date", "")).strip()
        end_date = str(payload.get("end_date", "")).strip()
        if not organization_id or not site_url or not start_date or not end_date:
            raise ProviderBadRequestError(
                "organization_id, site_url, start_date, and end_date are required for Search Console calls."
            )

        try:
            credentials = _resolve_google_credentials(self._db, organization_id)
        except ProviderCredentialConfigurationError as exc:
            raise ProviderAuthError(str(exc)) from exc
        access_token = str(credentials.get("access_token", "")).strip()
        if not access_token:
            raise ProviderAuthError("Google OAuth access token missing for Search Console provider.")
        expected_scope = get_settings().google_oauth_scope_gsc
        granted_scope = str(credentials.get("scope", "")).strip()
        if expected_scope and granted_scope and expected_scope not in granted_scope.split():
            raise ProviderAuthError("Google OAuth scope missing for Search Console provider.")

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
            required_metrics = ("clicks", "impressions", "ctr", "position")
            if any(metric not in item for metric in required_metrics):
                raise ProviderResponseFormatError(
                    "Google Search Console changed a measurement row that InsightOS has not reviewed yet."
                )
            keys = item.get("keys", [])
            if not isinstance(keys, list):
                keys = []
            try:
                metrics.append(
                    SearchMetrics(
                        query=str(keys[0]) if keys else "",
                        clicks=float(item["clicks"]),
                        impressions=float(item["impressions"]),
                        ctr=float(item["ctr"]),
                        position=float(item["position"]),
                        keys=[str(v) for v in keys],
                    )
                )
            except (TypeError, ValueError) as exc:
                raise ProviderResponseFormatError(
                    "Google Search Console returned an unreadable measurement row."
                ) from exc

        return {
            "dataset": "search_metrics",
            "rows": [asdict(m) for m in metrics],
            "row_count": len(metrics),
        }


class SearchConsoleSiteIntegrityAdapter(ProviderBase):
    provider_version = "google-search-console-site-integrity-v1"
    capability = "search_console_site_integrity"

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
        self._timeout_seconds = float(
            timeout_seconds or settings.google_oauth_http_timeout_seconds
        )
        self._inspection_endpoint = (
            "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
        )
        self._webmasters_endpoint = "https://www.googleapis.com/webmasters/v3"

    def _execute_impl(self, request: ProviderExecutionRequest) -> dict:
        try:
            standards_source_service.assert_provider_contract_ready(
                self._db,
                "google_search_console",
            )
        except standards_source_service.StandardsContractBlockedError as exc:
            raise ProviderContractReviewError(str(exc)) from exc

        payload = request.payload
        organization_id = str(payload.get("organization_id", "")).strip()
        site_url = str(payload.get("site_url", "")).strip()
        if not organization_id or not site_url:
            raise ProviderBadRequestError(
                "organization_id and site_url are required for Search Console site integrity calls."
            )

        credentials = self._credentials(organization_id)
        timeout_seconds = _resolve_timeout_seconds(payload, self._timeout_seconds)
        if request.operation == "url_inspection":
            inspection_url = str(payload.get("inspection_url", "")).strip()
            if not inspection_url:
                raise ProviderBadRequestError("inspection_url is required for URL inspection.")
            return self._inspect_url(
                credentials=credentials,
                site_url=site_url,
                inspection_url=inspection_url,
                timeout_seconds=timeout_seconds,
            )
        if request.operation == "sitemaps_list":
            return self._list_sitemaps(
                credentials=credentials,
                site_url=site_url,
                timeout_seconds=timeout_seconds,
            )
        raise ProviderBadRequestError("Unsupported Search Console site integrity operation.")

    def _credentials(self, organization_id: str) -> dict[str, Any]:
        try:
            credentials = _resolve_google_credentials(self._db, organization_id)
        except ProviderCredentialConfigurationError as exc:
            raise ProviderAuthError(str(exc)) from exc
        access_token = str(credentials.get("access_token", "")).strip()
        if not access_token:
            raise ProviderAuthError("Google OAuth access token missing for Search Console provider.")
        expected_scope = get_settings().google_oauth_scope_gsc
        granted_scope = str(credentials.get("scope", "")).strip()
        if expected_scope and granted_scope and expected_scope not in granted_scope.split():
            raise ProviderAuthError("Google OAuth scope missing for Search Console provider.")
        return credentials

    def _inspect_url(
        self,
        *,
        credentials: dict[str, Any],
        site_url: str,
        inspection_url: str,
        timeout_seconds: float,
    ) -> dict:
        body = self._request_json(
            "POST",
            self._inspection_endpoint,
            credentials=credentials,
            timeout_seconds=timeout_seconds,
            json_body={
                "inspectionUrl": inspection_url,
                "siteUrl": site_url,
                "languageCode": "en-US",
            },
        )
        inspection_result = body.get("inspectionResult")
        if not isinstance(inspection_result, dict):
            raise ProviderResponseFormatError(
                "Google Search Console URL inspection result is missing."
            )
        index_result = inspection_result.get("indexStatusResult")
        if not isinstance(index_result, dict):
            raise ProviderResponseFormatError(
                "Google Search Console index status result is missing."
            )
        record = UrlInspectionRecord(
            inspection_url=inspection_url,
            site_url=site_url,
            verdict=str(index_result.get("verdict") or "VERDICT_UNSPECIFIED"),
            coverage_state=_optional_string(index_result.get("coverageState")),
            robots_txt_state=_optional_string(index_result.get("robotsTxtState")),
            indexing_state=_optional_string(index_result.get("indexingState")),
            page_fetch_state=_optional_string(index_result.get("pageFetchState")),
            google_canonical=_optional_string(index_result.get("googleCanonical")),
            user_canonical=_optional_string(index_result.get("userCanonical")),
            crawled_as=_optional_string(index_result.get("crawledAs")),
            last_crawl_time=_optional_string(index_result.get("lastCrawlTime")),
            sitemap_urls=_string_list(index_result.get("sitemap")),
            referring_urls=_string_list(index_result.get("referringUrls")),
        )
        return {"dataset": "url_inspection", "record": asdict(record)}

    def _list_sitemaps(
        self,
        *,
        credentials: dict[str, Any],
        site_url: str,
        timeout_seconds: float,
    ) -> dict:
        endpoint = f"{self._webmasters_endpoint}/sites/{quote(site_url, safe='')}/sitemaps"
        body = self._request_json(
            "GET",
            endpoint,
            credentials=credentials,
            timeout_seconds=timeout_seconds,
        )
        raw_sitemaps = body.get("sitemap", [])
        if not isinstance(raw_sitemaps, list):
            raise ProviderResponseFormatError(
                "Google Search Console sitemaps response must contain a list."
            )
        records: list[SitemapRecord] = []
        for item in raw_sitemaps:
            if not isinstance(item, dict):
                raise ProviderResponseFormatError(
                    "Google Search Console returned an unreadable sitemap record."
                )
            sitemap_url = str(item.get("path") or "").strip()
            if not sitemap_url:
                raise ProviderResponseFormatError(
                    "Google Search Console returned a sitemap without a path."
                )
            contents = _sitemap_contents(item.get("contents"))
            records.append(
                SitemapRecord(
                    site_url=site_url,
                    sitemap_url=sitemap_url,
                    sitemap_type=_optional_string(item.get("type")),
                    is_pending=bool(item.get("isPending", False)),
                    is_sitemaps_index=bool(item.get("isSitemapsIndex", False)),
                    warnings=_non_negative_int(item.get("warnings")),
                    errors=_non_negative_int(item.get("errors")),
                    submitted_url_count=sum(
                        _non_negative_int(content.get("submitted")) for content in contents
                    ),
                    contents=contents,
                    last_submitted_at=_optional_string(item.get("lastSubmitted")),
                    last_downloaded_at=_optional_string(item.get("lastDownloaded")),
                )
            )
        return {
            "dataset": "sitemaps",
            "rows": [asdict(record) for record in records],
            "row_count": len(records),
        }

    def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        credentials: dict[str, Any],
        timeout_seconds: float,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            with httpx.Client() as client:
                response = client.request(
                    method,
                    endpoint,
                    json=json_body,
                    headers={"Authorization": f"Bearer {credentials['access_token']}"},
                    timeout=timeout_seconds,
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Google Search Console request timed out.") from exc
        except httpx.ConnectError as exc:
            raise ProviderConnectionError("Google Search Console connection failed.") from exc
        except httpx.HTTPError as exc:
            raise ProviderDependencyError(
                "Google Search Console dependency call failed."
            ) from exc
        if response.status_code >= 400:
            _raise_for_google_error(response, service_name="Search Console")
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderResponseFormatError(
                "Google Search Console response is not valid JSON."
            ) from exc
        if not isinstance(body, dict):
            raise ProviderResponseFormatError(
                "Google Search Console response must be a JSON object."
            )
        return body


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


def _optional_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _sitemap_contents(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "type": str(item.get("type") or "unknown"),
                "submitted": _non_negative_int(item.get("submitted")),
            }
        )
    return normalized


def _resolve_google_credentials(db: Session, organization_id: str) -> dict[str, Any]:
    try:
        return resolve_provider_credentials(
            db,
            organization_id,
            "google",
            required_credential_mode="byo_required",
            require_org_oauth=True,
        )
    except TypeError:
        # Backward compatibility for tests that monkeypatch a legacy 3-arg resolver.
        return resolve_provider_credentials(db, organization_id, "google")


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
