from __future__ import annotations

from datetime import date
from typing import Any

import httpx


ACCOUNT_API = "https://mybusinessaccountmanagement.googleapis.com/v1"
BUSINESS_INFO_API = "https://mybusinessbusinessinformation.googleapis.com/v1"
PERFORMANCE_API = "https://businessprofileperformance.googleapis.com/v1"
PROFILE_READ_MASK = ",".join(
    (
        "name",
        "languageCode",
        "storeCode",
        "title",
        "phoneNumbers",
        "categories",
        "storefrontAddress",
        "websiteUri",
        "regularHours",
        "specialHours",
        "serviceArea",
        "latlng",
        "openInfo",
        "metadata",
        "profile",
        "moreHours",
        "serviceItems",
    )
)
DAILY_METRICS = (
    "BUSINESS_IMPRESSIONS_DESKTOP_MAPS",
    "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH",
    "BUSINESS_IMPRESSIONS_MOBILE_MAPS",
    "BUSINESS_IMPRESSIONS_MOBILE_SEARCH",
    "BUSINESS_DIRECTION_REQUESTS",
    "CALL_CLICKS",
    "WEBSITE_CLICKS",
    "BUSINESS_BOOKINGS",
)


class GoogleBusinessProfileProviderError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def discover_profiles(
    *,
    access_token: str,
    timeout_seconds: float = 20,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    accounts = _paged_get(
        f"{ACCOUNT_API}/accounts",
        collection_key="accounts",
        access_token=access_token,
        timeout_seconds=timeout_seconds,
        client=client,
    )
    profiles: list[dict[str, Any]] = []
    for account in accounts:
        account_name = str(account.get("name") or "").strip()
        if not account_name.startswith("accounts/"):
            continue
        locations = _paged_get(
            f"{BUSINESS_INFO_API}/{account_name}/locations",
            collection_key="locations",
            access_token=access_token,
            timeout_seconds=timeout_seconds,
            client=client,
            params={"readMask": PROFILE_READ_MASK, "pageSize": "100"},
        )
        for location in locations:
            resource_id = str(location.get("name") or "").strip()
            if not resource_id.startswith("locations/"):
                continue
            profiles.append(
                {
                    "id": resource_id,
                    "name": str(location.get("title") or resource_id),
                    "account_id": account_name,
                    "account_name": str(account.get("accountName") or "Google account"),
                    "account_role": str(account.get("role") or "UNKNOWN"),
                    "permission_level": str(account.get("permissionLevel") or "UNKNOWN"),
                    "verified": _profile_is_verified(location, account),
                    "address": _format_address(location.get("storefrontAddress")),
                    "website": str(location.get("websiteUri") or ""),
                    "phone": _primary_phone(location),
                    "primary_category": _primary_category(location),
                    "profile": location,
                }
            )
    return sorted(profiles, key=lambda item: (item["name"].lower(), item["address"].lower()))


def get_profile(
    *,
    access_token: str,
    resource_id: str,
    timeout_seconds: float = 20,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    payload = _get_json(
        f"{BUSINESS_INFO_API}/{resource_id}",
        access_token=access_token,
        timeout_seconds=timeout_seconds,
        client=client,
        params={"readMask": PROFILE_READ_MASK},
    )
    attributes = _get_json(
        f"{BUSINESS_INFO_API}/{resource_id}/attributes",
        access_token=access_token,
        timeout_seconds=timeout_seconds,
        client=client,
        allow_not_found=True,
    )
    payload["attributes"] = attributes.get("attributes", [])
    return payload


def fetch_daily_metrics(
    *,
    access_token: str,
    resource_id: str,
    date_from: date,
    date_to: date,
    timeout_seconds: float = 20,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    params: list[tuple[str, str]] = [("dailyMetrics", metric) for metric in DAILY_METRICS]
    params.extend(
        (
            ("dailyRange.startDate.year", str(date_from.year)),
            ("dailyRange.startDate.month", str(date_from.month)),
            ("dailyRange.startDate.day", str(date_from.day)),
            ("dailyRange.endDate.year", str(date_to.year)),
            ("dailyRange.endDate.month", str(date_to.month)),
            ("dailyRange.endDate.day", str(date_to.day)),
        )
    )
    payload = _get_json(
        f"{PERFORMANCE_API}/{resource_id}:fetchMultiDailyMetricsTimeSeries",
        access_token=access_token,
        timeout_seconds=timeout_seconds,
        client=client,
        params=params,
    )
    rows: list[dict[str, Any]] = []
    groups = payload.get("multiDailyMetricTimeSeries", [])
    if not isinstance(groups, list):
        return rows
    for group in groups:
        if not isinstance(group, dict):
            continue
        series_rows = group.get("dailyMetricTimeSeries", [])
        if not isinstance(series_rows, list):
            continue
        for series in series_rows:
            if not isinstance(series, dict):
                continue
            metric_name = str(series.get("dailyMetric") or "").strip()
            if metric_name and metric_name not in DAILY_METRICS:
                raise GoogleBusinessProfileProviderError(
                    "Google changed a business listing measurement that InsightOS has not reviewed yet.",
                    reason_code="provider_contract_unknown",
                    status_code=409,
                )
            dated_values = (series.get("timeSeries") or {}).get("datedValues", [])
            if not metric_name or not isinstance(dated_values, list):
                continue
            for point in dated_values:
                if not isinstance(point, dict) or not isinstance(point.get("date"), dict):
                    continue
                point_date = _parse_google_date(point["date"])
                if point_date is None:
                    continue
                rows.append(
                    {
                        "metric_name": metric_name,
                        "metric_date": point_date,
                        "metric_value": int(point.get("value") or 0),
                        "missing_reason": None,
                    }
                )
    return rows


def fetch_search_keywords(
    *,
    access_token: str,
    resource_id: str,
    month_from: date,
    month_to: date,
    timeout_seconds: float = 20,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    rows = _paged_get(
        f"{PERFORMANCE_API}/{resource_id}/searchkeywords/impressions/monthly",
        collection_key="searchKeywordsCounts",
        access_token=access_token,
        timeout_seconds=timeout_seconds,
        client=client,
        params={
            "monthlyRange.startMonth.year": str(month_from.year),
            "monthlyRange.startMonth.month": str(month_from.month),
            "monthlyRange.endMonth.year": str(month_to.year),
            "monthlyRange.endMonth.month": str(month_to.month),
            "pageSize": "100",
        },
    )
    normalized: list[dict[str, Any]] = []
    for row in rows:
        keyword = str(row.get("searchKeyword") or "").strip().lower()
        value = row.get("insightsValue") or {}
        if not keyword or not isinstance(value, dict):
            continue
        if "value" in value:
            impressions = int(value.get("value") or 0)
            measurement = "exact"
        elif "threshold" in value:
            impressions = int(value.get("threshold") or 0)
            measurement = "below_threshold"
        else:
            raise GoogleBusinessProfileProviderError(
                "Google changed a search-term measurement that InsightOS has not reviewed yet.",
                reason_code="provider_contract_unknown",
                status_code=409,
            )
        normalized.append(
            {
                "keyword": keyword,
                "impressions": impressions,
                "measurement": measurement,
            }
        )
    return normalized


def _paged_get(
    url: str,
    *,
    collection_key: str,
    access_token: str,
    timeout_seconds: float,
    client: httpx.Client | None,
    params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_token = ""
    for _page in range(50):
        page_params = dict(params or {})
        if page_token:
            page_params["pageToken"] = page_token
        payload = _get_json(
            url,
            access_token=access_token,
            timeout_seconds=timeout_seconds,
            client=client,
            params=page_params,
        )
        page_rows = payload.get(collection_key, [])
        if isinstance(page_rows, list):
            rows.extend(item for item in page_rows if isinstance(item, dict))
        page_token = str(payload.get("nextPageToken") or "").strip()
        if not page_token:
            break
    return rows


def _get_json(
    url: str,
    *,
    access_token: str,
    timeout_seconds: float,
    client: httpx.Client | None,
    params: Any = None,
    allow_not_found: bool = False,
) -> dict[str, Any]:
    own_client = client is None
    resolved_client = client or httpx.Client()
    try:
        response = resolved_client.get(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-GOOG-API-FORMAT-VERSION": "2",
            },
            params=params,
            timeout=timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise GoogleBusinessProfileProviderError(
            "Google took too long to return the business listing.",
            reason_code="provider_timeout",
            status_code=504,
        ) from exc
    except httpx.HTTPError as exc:
        raise GoogleBusinessProfileProviderError(
            "Google business listing data could not be reached.",
            reason_code="provider_unavailable",
            status_code=502,
        ) from exc
    finally:
        if own_client:
            resolved_client.close()

    if allow_not_found and response.status_code == 404:
        return {}
    if response.status_code == 401:
        raise GoogleBusinessProfileProviderError(
            "Reconnect Google to continue.",
            reason_code="oauth_reconnect_required",
            status_code=409,
        )
    if response.status_code == 403:
        raise GoogleBusinessProfileProviderError(
            "Google business listing access is not approved for this Google Cloud project yet.",
            reason_code="business_profile_api_access_required",
            status_code=409,
        )
    if response.status_code >= 400:
        raise GoogleBusinessProfileProviderError(
            "Google could not return the business listing right now.",
            reason_code="provider_request_failed",
            status_code=502,
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise GoogleBusinessProfileProviderError(
            "Google returned an unreadable business listing response.",
            reason_code="provider_response_invalid",
            status_code=502,
        ) from exc
    if not isinstance(payload, dict):
        raise GoogleBusinessProfileProviderError(
            "Google returned an unreadable business listing response.",
            reason_code="provider_response_invalid",
            status_code=502,
        )
    return payload


def _parse_google_date(value: dict[str, Any]) -> date | None:
    try:
        return date(int(value["year"]), int(value["month"]), int(value["day"]))
    except (KeyError, TypeError, ValueError):
        return None


def _format_address(raw: Any) -> str:
    if not isinstance(raw, dict):
        return ""
    parts = list(raw.get("addressLines") or [])
    for key in ("locality", "administrativeArea", "postalCode"):
        value = str(raw.get(key) or "").strip()
        if value:
            parts.append(value)
    return ", ".join(str(part).strip() for part in parts if str(part).strip())


def _primary_phone(location: dict[str, Any]) -> str:
    value = location.get("phoneNumbers") or {}
    return str(value.get("primaryPhone") or "") if isinstance(value, dict) else ""


def _primary_category(location: dict[str, Any]) -> str:
    categories = location.get("categories") or {}
    primary = categories.get("primaryCategory") or {} if isinstance(categories, dict) else {}
    return str(primary.get("displayName") or primary.get("name") or "") if isinstance(primary, dict) else ""


def _profile_is_verified(location: dict[str, Any], account: dict[str, Any]) -> bool:
    metadata = location.get("metadata") or {}
    if isinstance(metadata, dict) and metadata.get("hasVoiceOfMerchant") is True:
        return True
    return str(account.get("verificationState") or "").upper() == "VERIFIED"
