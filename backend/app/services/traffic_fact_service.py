from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import json
import os
from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models.analytics_daily_metric import AnalyticsDailyMetric
from app.models.campaign import Campaign
from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.providers.execution_types import ProviderExecutionRequest
from app.providers.google_analytics import GoogleAnalyticsProviderAdapter
from app.providers.google_search_console import SearchConsoleProviderAdapter
from app.services.provider_credentials_service import resolve_provider_credentials


@dataclass(frozen=True)
class SearchConsoleDailyMetricInput:
    organization_id: str
    campaign_id: str
    metric_date: date
    clicks: int
    impressions: int
    avg_position: float | None


@dataclass(frozen=True)
class AnalyticsDailyMetricInput:
    organization_id: str
    campaign_id: str
    metric_date: date
    sessions: int
    conversions: int


@dataclass(frozen=True)
class MetricUpsertResult:
    inserted: bool
    updated: bool
    skipped: bool
    row_id: str | None
    deterministic_hash: str


@dataclass(frozen=True)
class TrafficFactSyncResult:
    organization_id: str
    campaign_id: str
    start_date: date
    end_date: date
    requested_days: int
    provider_calls: int
    inserted_rows: int
    updated_rows: int
    skipped_rows: int
    replay_skipped: bool = False


def upsert_search_console_daily_metric(*, db: Session, metric_input: SearchConsoleDailyMetricInput) -> MetricUpsertResult:
    payload = _normalize_search_console_daily_metric(metric_input)
    existing = (
        db.query(SearchConsoleDailyMetric)
        .filter(
            SearchConsoleDailyMetric.campaign_id == metric_input.campaign_id,
            SearchConsoleDailyMetric.metric_date == metric_input.metric_date,
        )
        .first()
    )
    if existing is None:
        row = SearchConsoleDailyMetric(**payload)
        db.add(row)
        db.flush()
        return MetricUpsertResult(True, False, False, row.id, row.deterministic_hash)
    if existing.deterministic_hash == payload['deterministic_hash']:
        return MetricUpsertResult(False, False, True, existing.id, existing.deterministic_hash)
    for key, value in payload.items():
        setattr(existing, key, value)
    db.flush()
    return MetricUpsertResult(False, True, False, existing.id, existing.deterministic_hash)


def upsert_analytics_daily_metric(*, db: Session, metric_input: AnalyticsDailyMetricInput) -> MetricUpsertResult:
    payload = _normalize_analytics_daily_metric(metric_input)
    existing = (
        db.query(AnalyticsDailyMetric)
        .filter(
            AnalyticsDailyMetric.campaign_id == metric_input.campaign_id,
            AnalyticsDailyMetric.metric_date == metric_input.metric_date,
        )
        .first()
    )
    if existing is None:
        row = AnalyticsDailyMetric(**payload)
        db.add(row)
        db.flush()
        return MetricUpsertResult(True, False, False, row.id, row.deterministic_hash)
    if existing.deterministic_hash == payload['deterministic_hash']:
        return MetricUpsertResult(False, False, True, existing.id, existing.deterministic_hash)
    for key, value in payload.items():
        setattr(existing, key, value)
    db.flush()
    return MetricUpsertResult(False, True, False, existing.id, existing.deterministic_hash)


def sync_search_console_daily_metrics_for_campaign(
    *,
    db: Session,
    campaign: Campaign,
    start_date: date | str,
    end_date: date | str,
) -> TrafficFactSyncResult:
    resolved_start = _coerce_date(start_date)
    resolved_end = _coerce_date(end_date)
    _validate_range(resolved_start, resolved_end)
    organization_id = _require_organization_id(campaign)
    missing_dates = _missing_metric_dates(
        db=db,
        model=SearchConsoleDailyMetric,
        campaign_id=campaign.id,
        start_date=resolved_start,
        end_date=resolved_end,
    )
    if not missing_dates:
        return TrafficFactSyncResult(organization_id, campaign.id, resolved_start, resolved_end, 0, 0, 0, 0, 0)
    if _replay_mode_enabled():
        return TrafficFactSyncResult(
            organization_id,
            campaign.id,
            resolved_start,
            resolved_end,
            len(missing_dates),
            0,
            0,
            0,
            0,
            replay_skipped=True,
        )

    credentials = resolve_provider_credentials(db, organization_id, 'google')
    site_url = _resolve_site_url(credentials=credentials, campaign=campaign)
    adapter = SearchConsoleProviderAdapter(db=db)

    metrics_by_day: dict[date, dict[str, float]] = {}
    provider_calls = 0
    for range_start, range_end in _iter_missing_ranges(missing_dates):
        provider_calls += 1
        result = adapter.execute(
            ProviderExecutionRequest(
                operation='search_console_query',
                payload={
                    'organization_id': organization_id,
                    'campaign_id': campaign.id,
                    'site_url': site_url,
                    'start_date': range_start.isoformat(),
                    'end_date': range_end.isoformat(),
                    'dimensions': ['date'],
                    'row_limit': 1000,
                },
            )
        )
        if not result.success:
            raise RuntimeError('Search Console provider call failed.')
        for row in _rows(result.raw_payload):
            row_date = _extract_row_date(row)
            if row_date is None or row_date not in missing_dates:
                continue
            entry = metrics_by_day.setdefault(row_date, {'clicks': 0.0, 'impressions': 0.0, 'position_weighted_sum': 0.0})
            entry['clicks'] += _safe_float(row.get('clicks'))
            entry['impressions'] += _safe_float(row.get('impressions'))
            impressions = _safe_float(row.get('impressions'))
            if impressions > 0:
                entry['position_weighted_sum'] += impressions * _safe_float(row.get('position'))

    inserted_rows = 0
    updated_rows = 0
    skipped_rows = 0
    for metric_day in missing_dates:
        values = metrics_by_day.get(metric_day, {'clicks': 0.0, 'impressions': 0.0, 'position_weighted_sum': 0.0})
        impressions = float(values['impressions'])
        avg_position = (float(values['position_weighted_sum']) / impressions) if impressions > 0 else None
        outcome = upsert_search_console_daily_metric(
            db=db,
            metric_input=SearchConsoleDailyMetricInput(
                organization_id=organization_id,
                campaign_id=campaign.id,
                metric_date=metric_day,
                clicks=int(round(float(values['clicks']))),
                impressions=int(round(impressions)),
                avg_position=avg_position,
            ),
        )
        inserted_rows += int(outcome.inserted)
        updated_rows += int(outcome.updated)
        skipped_rows += int(outcome.skipped)
    if inserted_rows or updated_rows:
        db.commit()

    return TrafficFactSyncResult(
        organization_id,
        campaign.id,
        resolved_start,
        resolved_end,
        len(missing_dates),
        provider_calls,
        inserted_rows,
        updated_rows,
        skipped_rows,
    )


def sync_analytics_daily_metrics_for_campaign(
    *,
    db: Session,
    campaign: Campaign,
    start_date: date | str,
    end_date: date | str,
) -> TrafficFactSyncResult:
    resolved_start = _coerce_date(start_date)
    resolved_end = _coerce_date(end_date)
    _validate_range(resolved_start, resolved_end)
    organization_id = _require_organization_id(campaign)
    missing_dates = _missing_metric_dates(
        db=db,
        model=AnalyticsDailyMetric,
        campaign_id=campaign.id,
        start_date=resolved_start,
        end_date=resolved_end,
    )
    if not missing_dates:
        return TrafficFactSyncResult(organization_id, campaign.id, resolved_start, resolved_end, 0, 0, 0, 0, 0)
    if _replay_mode_enabled():
        return TrafficFactSyncResult(
            organization_id,
            campaign.id,
            resolved_start,
            resolved_end,
            len(missing_dates),
            0,
            0,
            0,
            0,
            replay_skipped=True,
        )

    credentials = resolve_provider_credentials(db, organization_id, 'google')
    property_id = _resolve_property_id(credentials=credentials)
    if not property_id:
        raise ValueError('Google Analytics property id missing for campaign traffic fact sync.')
    adapter = GoogleAnalyticsProviderAdapter(db=db)

    metrics_by_day: dict[date, dict[str, float]] = {}
    provider_calls = 0
    for range_start, range_end in _iter_missing_ranges(missing_dates):
        provider_calls += 1
        result = adapter.execute(
            ProviderExecutionRequest(
                operation='ga4_run_report',
                payload={
                    'organization_id': organization_id,
                    'campaign_id': campaign.id,
                    'property_id': property_id,
                    'start_date': range_start.isoformat(),
                    'end_date': range_end.isoformat(),
                    'dimensions': ['date'],
                    'metrics': ['sessions', 'conversions'],
                    'limit': 1000,
                },
            )
        )
        if not result.success:
            raise RuntimeError('Google Analytics provider call failed.')
        for row in _rows(result.raw_payload):
            row_date = _extract_row_date(row)
            if row_date is None or row_date not in missing_dates:
                continue
            entry = metrics_by_day.setdefault(row_date, {'sessions': 0.0, 'conversions': 0.0})
            entry['sessions'] += _safe_float(_metric_value(row, 'sessions'))
            entry['conversions'] += _safe_float(_metric_value(row, 'conversions'))

    inserted_rows = 0
    updated_rows = 0
    skipped_rows = 0
    for metric_day in missing_dates:
        values = metrics_by_day.get(metric_day, {'sessions': 0.0, 'conversions': 0.0})
        outcome = upsert_analytics_daily_metric(
            db=db,
            metric_input=AnalyticsDailyMetricInput(
                organization_id=organization_id,
                campaign_id=campaign.id,
                metric_date=metric_day,
                sessions=int(round(float(values['sessions']))),
                conversions=int(round(float(values['conversions']))),
            ),
        )
        inserted_rows += int(outcome.inserted)
        updated_rows += int(outcome.updated)
        skipped_rows += int(outcome.skipped)
    if inserted_rows or updated_rows:
        db.commit()

    return TrafficFactSyncResult(
        organization_id,
        campaign.id,
        resolved_start,
        resolved_end,
        len(missing_dates),
        provider_calls,
        inserted_rows,
        updated_rows,
        skipped_rows,
    )


def _normalize_search_console_daily_metric(metric_input: SearchConsoleDailyMetricInput) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'organization_id': metric_input.organization_id,
        'campaign_id': metric_input.campaign_id,
        'metric_date': metric_input.metric_date,
        'clicks': int(metric_input.clicks),
        'impressions': int(metric_input.impressions),
        'avg_position': metric_input.avg_position,
    }
    payload['deterministic_hash'] = _stable_hash(payload)
    return payload


def _normalize_analytics_daily_metric(metric_input: AnalyticsDailyMetricInput) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'organization_id': metric_input.organization_id,
        'campaign_id': metric_input.campaign_id,
        'metric_date': metric_input.metric_date,
        'sessions': int(metric_input.sessions),
        'conversions': int(metric_input.conversions),
    }
    payload['deterministic_hash'] = _stable_hash(payload)
    return payload


def _stable_hash(payload: dict[str, Any]) -> str:
    serialized = {key: _serialize_value(value) for key, value in payload.items()}
    encoded = json.dumps(serialized, sort_keys=True, separators=(',', ':'))
    return sha256(encoded.encode('utf-8')).hexdigest()


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return format(value, '.15g')
    return value


def _coerce_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def _validate_range(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise ValueError('end_date must be on or after start_date')


def _require_organization_id(campaign: Campaign) -> str:
    if not campaign.organization_id:
        raise ValueError(f'Campaign {campaign.id} is missing organization_id and cannot sync traffic facts')
    return str(campaign.organization_id)


def _missing_metric_dates(*, db: Session, model: type[SearchConsoleDailyMetric] | type[AnalyticsDailyMetric], campaign_id: str, start_date: date, end_date: date) -> list[date]:
    existing_dates = {
        row[0]
        for row in (
            db.query(model.metric_date)
            .filter(
                model.campaign_id == campaign_id,
                model.metric_date >= start_date,
                model.metric_date <= end_date,
            )
            .all()
        )
    }
    return [metric_day for metric_day in _iter_days(start_date, end_date) if metric_day not in existing_dates]


def _iter_missing_ranges(days: list[date]) -> list[tuple[date, date]]:
    if not days:
        return []
    ordered = sorted(days)
    ranges: list[tuple[date, date]] = []
    start = ordered[0]
    end = ordered[0]
    for current in ordered[1:]:
        if current == end + timedelta(days=1):
            end = current
            continue
        ranges.append((start, end))
        start = current
        end = current
    ranges.append((start, end))
    return ranges


def _iter_days(start: date, end: date) -> list[date]:
    days: list[date] = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _rows(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get('rows')
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _extract_row_date(row: dict[str, Any]) -> date | None:
    candidates: list[Any] = []
    if 'date' in row:
        candidates.append(row.get('date'))
    keys = row.get('keys')
    if isinstance(keys, list) and keys:
        candidates.append(keys[0])
    dim_values = row.get('dimension_values')
    if isinstance(dim_values, dict) and 'date' in dim_values:
        candidates.append(dim_values.get('date'))
    dim_values_alt = row.get('dimensionValues')
    if isinstance(dim_values_alt, list) and dim_values_alt:
        first_value = dim_values_alt[0]
        if isinstance(first_value, dict):
            candidates.append(first_value.get('value'))
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
            return datetime.strptime(raw, '%Y%m%d').date()
        except ValueError:
            return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _metric_value(row: dict[str, Any], name: str) -> float | None:
    metrics = row.get('metric_values')
    if not isinstance(metrics, dict):
        return None
    value = metrics.get(name)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _resolve_site_url(*, credentials: dict[str, Any], campaign: Campaign) -> str:
    site_url = str(credentials.get('search_console_site_url', '')).strip()
    if site_url:
        return site_url
    return f'sc-domain:{campaign.domain}'


def _resolve_property_id(*, credentials: dict[str, Any]) -> str:
    value = credentials.get('ga4_property_id') or credentials.get('property_id') or ''
    return str(value).strip()


def _replay_mode_enabled() -> bool:
    return os.getenv('LSOS_REPLAY_MODE', '0').strip() == '1' or os.getenv('REPLAY_MODE', '0').strip() == '1'
