from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import log10
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.providers.execution_types import ProviderExecutionRequest
from app.providers.google_analytics import GoogleAnalyticsProviderAdapter
from app.providers.google_search_console import SearchConsoleProviderAdapter
from app.services.provider_credentials_service import resolve_provider_credentials

OPPORTUNITY_IMPRESSIONS_THRESHOLD = 1000.0
OPPORTUNITY_CTR_THRESHOLD = 0.02
DECLINE_SESSIONS_DROP_THRESHOLD_PERCENT = 20.0


@dataclass(frozen=True)
class WindowMetrics:
    clicks: float
    impressions: float
    ctr: float
    avg_position: float | None
    sessions: float
    conversions: float | None


@dataclass(frozen=True)
class TrendPoint:
    period_start: date
    period_end: date
    clicks: float
    impressions: float
    ctr: float
    avg_position: float
    sessions: float
    conversions: float
    visibility_score: float


def build_campaign_performance_summary(
    db: Session,
    *,
    campaign: Campaign,
    date_from: datetime,
    date_to: datetime,
) -> dict:
    organization_id = campaign.tenant_id
    credentials = resolve_provider_credentials(db, organization_id, "google")
    site_url = _resolve_site_url(credentials=credentials, campaign=campaign)
    property_id = _resolve_property_id(credentials=credentials)

    previous_date_from, previous_date_to = _previous_window_bounds(date_from=date_from, date_to=date_to)
    current = _window_metrics(
        db=db,
        organization_id=organization_id,
        campaign_id=campaign.id,
        site_url=site_url,
        property_id=property_id,
        date_from=date_from,
        date_to=date_to,
    )
    previous = _window_metrics(
        db=db,
        organization_id=organization_id,
        campaign_id=campaign.id,
        site_url=site_url,
        property_id=property_id,
        date_from=previous_date_from,
        date_to=previous_date_to,
    )
    visibility_score = _visibility_score(
        impressions=current.impressions,
        avg_position=current.avg_position,
        ctr=current.ctr,
    )
    traffic_growth_percent = _percent_growth(
        current_value=current.sessions,
        previous_value=previous.sessions,
    )
    position_delta = _position_delta(
        current_position=current.avg_position,
        previous_position=previous.avg_position,
    )
    opportunity_flag = (
        current.impressions >= OPPORTUNITY_IMPRESSIONS_THRESHOLD
        and current.ctr <= OPPORTUNITY_CTR_THRESHOLD
    )
    decline_flag = _decline_flag(
        current_sessions=current.sessions,
        previous_sessions=previous.sessions,
    )

    return {
        "campaign_id": campaign.id,
        "date_from": _as_utc(date_from).isoformat(),
        "date_to": _as_utc(date_to).isoformat(),
        "clicks": current.clicks,
        "impressions": current.impressions,
        "ctr": current.ctr,
        "avg_position": current.avg_position,
        "sessions": current.sessions,
        "conversions": current.conversions,
        "visibility_score": visibility_score,
        "traffic_growth_percent": traffic_growth_percent,
        "position_delta": position_delta,
        "opportunity_flag": opportunity_flag,
        "decline_flag": decline_flag,
    }


def build_campaign_performance_trend(
    db: Session,
    *,
    campaign: Campaign,
    date_from: date,
    date_to: date,
    interval: Literal["day", "week", "month"],
) -> dict[str, Any]:
    organization_id = campaign.tenant_id
    credentials = resolve_provider_credentials(db, organization_id, "google")
    site_url = _resolve_site_url(credentials=credentials, campaign=campaign)
    property_id = _resolve_property_id(credentials=credentials)

    daily_search = _daily_search_metrics(
        db=db,
        organization_id=organization_id,
        campaign_id=campaign.id,
        site_url=site_url,
        date_from=date_from,
        date_to=date_to,
    )
    daily_ga = _daily_ga_metrics(
        db=db,
        organization_id=organization_id,
        campaign_id=campaign.id,
        property_id=property_id,
        date_from=date_from,
        date_to=date_to,
    )

    points: list[dict[str, Any]] = []
    for period_start, period_end in _iter_periods(date_from=date_from, date_to=date_to, interval=interval):
        bucket_dates = _iter_days(period_start, period_end)
        clicks = 0.0
        impressions = 0.0
        weighted_position_sum = 0.0
        sessions = 0.0
        conversions = 0.0

        for day in bucket_dates:
            search_metrics = daily_search.get(day, {"clicks": 0.0, "impressions": 0.0, "position_weighted_sum": 0.0})
            clicks += float(search_metrics["clicks"])
            impressions += float(search_metrics["impressions"])
            weighted_position_sum += float(search_metrics["position_weighted_sum"])
            ga_metrics = daily_ga.get(day, {"sessions": 0.0, "conversions": 0.0})
            sessions += float(ga_metrics["sessions"])
            conversions += float(ga_metrics["conversions"])

        ctr = (clicks / impressions) if impressions > 0 else 0.0
        avg_position_raw = (weighted_position_sum / impressions) if impressions > 0 else None
        visibility_score = _visibility_score(impressions=impressions, avg_position=avg_position_raw, ctr=ctr)

        point = TrendPoint(
            period_start=period_start,
            period_end=period_end,
            clicks=clicks,
            impressions=impressions,
            ctr=ctr,
            avg_position=avg_position_raw if avg_position_raw is not None else 0.0,
            sessions=sessions,
            conversions=conversions,
            visibility_score=visibility_score,
        )
        points.append(
            {
                "period_start": point.period_start.isoformat(),
                "period_end": point.period_end.isoformat(),
                "clicks": point.clicks,
                "impressions": point.impressions,
                "ctr": point.ctr,
                "avg_position": point.avg_position,
                "sessions": point.sessions,
                "conversions": point.conversions,
                "visibility_score": point.visibility_score,
            }
        )

    return {
        "campaign_id": campaign.id,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "interval": interval,
        "points": points,
    }


def _window_metrics(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    site_url: str,
    property_id: str,
    date_from: datetime,
    date_to: datetime,
) -> WindowMetrics:
    search_console = SearchConsoleProviderAdapter(db=db)
    search_result = search_console.execute(
        ProviderExecutionRequest(
            operation="search_console_query",
            payload={
                "organization_id": organization_id,
                "campaign_id": campaign_id,
                "site_url": site_url,
                "start_date": date_from.date().isoformat(),
                "end_date": date_to.date().isoformat(),
                "dimensions": ["query"],
                "row_limit": 1000,
            },
        )
    )
    if not search_result.success:
        raise RuntimeError("Search Console provider call failed.")

    search_rows = _rows(search_result.raw_payload)
    clicks = sum(float(row.get("clicks", 0.0)) for row in search_rows)
    impressions = sum(float(row.get("impressions", 0.0)) for row in search_rows)
    ctr = (clicks / impressions) if impressions > 0 else 0.0
    avg_position = _weighted_avg_position(search_rows)

    sessions = 0.0
    conversions: float | None = None
    if property_id:
        ga = GoogleAnalyticsProviderAdapter(db=db)
        ga_result = ga.execute(
            ProviderExecutionRequest(
                operation="ga4_run_report",
                payload={
                    "organization_id": organization_id,
                    "campaign_id": campaign_id,
                    "property_id": property_id,
                    "start_date": date_from.date().isoformat(),
                    "end_date": date_to.date().isoformat(),
                    "dimensions": ["date"],
                    "metrics": ["sessions", "conversions"],
                    "limit": 1000,
                },
            )
        )
        if not ga_result.success:
            raise RuntimeError("Google Analytics provider call failed.")
        ga_rows = _rows(ga_result.raw_payload)
        session_values: list[float] = []
        for row in ga_rows:
            value = _metric_value(row, "sessions")
            if value is not None:
                session_values.append(float(value))
        sessions = sum(session_values)
        conversion_values: list[float] = []
        for row in ga_rows:
            value = _metric_value(row, "conversions")
            if value is not None:
                conversion_values.append(float(value))
        conversions = sum(conversion_values) if conversion_values else None
    return WindowMetrics(
        clicks=clicks,
        impressions=impressions,
        ctr=ctr,
        avg_position=avg_position,
        sessions=sessions,
        conversions=conversions,
    )


def _daily_search_metrics(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    site_url: str,
    date_from: date,
    date_to: date,
) -> dict[date, dict[str, float]]:
    search_console = SearchConsoleProviderAdapter(db=db)
    search_result = search_console.execute(
        ProviderExecutionRequest(
            operation="search_console_query",
            payload={
                "organization_id": organization_id,
                "campaign_id": campaign_id,
                "site_url": site_url,
                "start_date": date_from.isoformat(),
                "end_date": date_to.isoformat(),
                "dimensions": ["date"],
                "row_limit": 1000,
            },
        )
    )
    if not search_result.success:
        raise RuntimeError("Search Console provider call failed.")

    metrics_by_day: dict[date, dict[str, float]] = {}
    for row in _rows(search_result.raw_payload):
        row_date = _extract_row_date(row)
        if row_date is None:
            continue
        clicks = _safe_float(row.get("clicks"))
        impressions = _safe_float(row.get("impressions"))
        position = _safe_float(row.get("position"))
        entry = metrics_by_day.setdefault(
            row_date,
            {"clicks": 0.0, "impressions": 0.0, "position_weighted_sum": 0.0},
        )
        entry["clicks"] += clicks
        entry["impressions"] += impressions
        if impressions > 0:
            entry["position_weighted_sum"] += impressions * position
    return metrics_by_day


def _daily_ga_metrics(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    property_id: str,
    date_from: date,
    date_to: date,
) -> dict[date, dict[str, float]]:
    if not property_id:
        return {}

    ga = GoogleAnalyticsProviderAdapter(db=db)
    ga_result = ga.execute(
        ProviderExecutionRequest(
            operation="ga4_run_report",
            payload={
                "organization_id": organization_id,
                "campaign_id": campaign_id,
                "property_id": property_id,
                "start_date": date_from.isoformat(),
                "end_date": date_to.isoformat(),
                "dimensions": ["date"],
                "metrics": ["sessions", "conversions"],
                "limit": 1000,
            },
        )
    )
    if not ga_result.success:
        raise RuntimeError("Google Analytics provider call failed.")

    metrics_by_day: dict[date, dict[str, float]] = {}
    for row in _rows(ga_result.raw_payload):
        row_date = _extract_row_date(row)
        if row_date is None:
            continue
        entry = metrics_by_day.setdefault(row_date, {"sessions": 0.0, "conversions": 0.0})
        entry["sessions"] += _safe_float(_metric_value(row, "sessions"))
        entry["conversions"] += _safe_float(_metric_value(row, "conversions"))
    return metrics_by_day


def _resolve_site_url(*, credentials: dict[str, Any], campaign: Campaign) -> str:
    site_url = str(credentials.get("search_console_site_url", "")).strip()
    if site_url:
        return site_url
    return f"sc-domain:{campaign.domain}"


def _resolve_property_id(*, credentials: dict[str, Any]) -> str:
    value = credentials.get("ga4_property_id") or credentials.get("property_id") or ""
    return str(value).strip()


def _previous_window_bounds(*, date_from: datetime, date_to: datetime) -> tuple[datetime, datetime]:
    window_days = (date_to.date() - date_from.date()).days + 1
    previous_date_to = date_from - timedelta(days=1)
    previous_date_from = previous_date_to - timedelta(days=window_days - 1)
    return previous_date_from, previous_date_to


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _visibility_score(*, impressions: float, avg_position: float | None, ctr: float) -> float:
    """Score 0-100.

    Formula:
    - impression_component = min((log10(impressions + 1) / 6) * 100, 100)
    - position_component = clamp((1 - ((avg_position - 1) / 49)) * 100, 0, 100)
    - ctr_component = min((ctr / 0.10) * 100, 100)
    - visibility_score = 0.40 * impression_component + 0.35 * position_component + 0.25 * ctr_component
    """
    impression_component = _clamp((log10(impressions + 1.0) / 6.0) * 100.0, 0.0, 100.0)
    position_raw = 0.0 if avg_position is None else (1.0 - ((avg_position - 1.0) / 49.0)) * 100.0
    position_component = _clamp(position_raw, 0.0, 100.0)
    ctr_component = _clamp((ctr / 0.10) * 100.0, 0.0, 100.0)
    return round((0.40 * impression_component) + (0.35 * position_component) + (0.25 * ctr_component), 2)


def _percent_growth(*, current_value: float, previous_value: float) -> float | None:
    if previous_value <= 0:
        return None
    return ((current_value - previous_value) / previous_value) * 100.0


def _position_delta(*, current_position: float | None, previous_position: float | None) -> float | None:
    if current_position is None or previous_position is None:
        return None
    return current_position - previous_position


def _decline_flag(*, current_sessions: float, previous_sessions: float) -> bool:
    if previous_sessions <= 0:
        return False
    drop_percent = ((previous_sessions - current_sessions) / previous_sessions) * 100.0
    return drop_percent > DECLINE_SESSIONS_DROP_THRESHOLD_PERCENT


def _metric_value(row: dict[str, Any], name: str) -> float | None:
    metrics = row.get("metric_values")
    if not isinstance(metrics, dict):
        return None
    value = metrics.get(name)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _rows(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _weighted_avg_position(rows: list[dict[str, Any]]) -> float | None:
    total_impressions = 0.0
    weighted_sum = 0.0
    for row in rows:
        impressions = float(row.get("impressions", 0.0))
        position = float(row.get("position", 0.0))
        if impressions > 0:
            total_impressions += impressions
            weighted_sum += impressions * position
    if total_impressions <= 0:
        return None
    return weighted_sum / total_impressions


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _extract_row_date(row: dict[str, Any]) -> date | None:
    candidates: list[Any] = []
    if "date" in row:
        candidates.append(row.get("date"))
    keys = row.get("keys")
    if isinstance(keys, list) and keys:
        candidates.append(keys[0])
    dim_values = row.get("dimension_values")
    if isinstance(dim_values, dict) and "date" in dim_values:
        candidates.append(dim_values.get("date"))
    dim_values_alt = row.get("dimensionValues")
    if isinstance(dim_values_alt, list) and dim_values_alt:
        first_value = dim_values_alt[0]
        if isinstance(first_value, dict):
            candidates.append(first_value.get("value"))
        else:
            candidates.append(first_value)

    for value in candidates:
        parsed = _parse_date_value(value)
        if parsed is not None:
            return parsed
    return None


def _parse_date_value(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if len(raw) == 8 and raw.isdigit():
        try:
            return datetime.strptime(raw, "%Y%m%d").date()
        except ValueError:
            return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _iter_days(start: date, end: date) -> list[date]:
    cursor = start
    values: list[date] = []
    while cursor <= end:
        values.append(cursor)
        cursor += timedelta(days=1)
    return values


def _iter_periods(
    *,
    date_from: date,
    date_to: date,
    interval: Literal["day", "week", "month"],
) -> list[tuple[date, date]]:
    if interval == "day":
        return [(day, day) for day in _iter_days(date_from, date_to)]

    periods: list[tuple[date, date]] = []
    cursor = date_from
    while cursor <= date_to:
        if interval == "week":
            days_to_end = 6 - cursor.weekday()
            period_end = min(date_to, cursor + timedelta(days=days_to_end))
        else:
            next_month = _first_of_next_month(cursor)
            period_end = min(date_to, next_month - timedelta(days=1))
        periods.append((cursor, period_end))
        cursor = period_end + timedelta(days=1)
    return periods


def _first_of_next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)
