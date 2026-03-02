from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from math import log10
from typing import Any, Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.analytics_daily_metric import AnalyticsDailyMetric
from app.models.campaign import Campaign
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.crawl import TechnicalIssue
from app.models.intelligence import IntelligenceScore
from app.models.local import ReviewVelocitySnapshot
from app.models.search_console_daily_metric import SearchConsoleDailyMetric

ANALYTICS_NORMALIZATION_VERSION = 'analytics-v1'
OPPORTUNITY_IMPRESSIONS_THRESHOLD = 1000.0
OPPORTUNITY_CTR_THRESHOLD = 0.02
DECLINE_SESSIONS_DROP_THRESHOLD_PERCENT = 20.0


@dataclass(frozen=True)
class CampaignDailyMetricInput:
    organization_id: str
    portfolio_id: str | None
    sub_account_id: str | None
    campaign_id: str
    metric_date: date
    clicks: int | None = None
    impressions: int | None = None
    avg_position: float | None = None
    sessions: int | None = None
    conversions: int | None = None
    technical_issue_count: int = 0
    intelligence_score: float | None = None
    reviews_last_30d: int = 0
    avg_rating_last_30d: float | None = None
    cost: Decimal | None = None
    revenue: Decimal | None = None
    normalization_version: str = ANALYTICS_NORMALIZATION_VERSION


@dataclass(frozen=True)
class CampaignDailyMetricUpsertResult:
    inserted: bool
    updated: bool
    skipped: bool
    row_id: str | None
    deterministic_hash: str


@dataclass(frozen=True)
class CampaignDailyMetricRollupResult:
    metric_date: date
    processed_campaigns: int
    inserted_rows: int
    updated_rows: int
    skipped_rows: int


@dataclass(frozen=True)
class CampaignDailyMetricRangeRollupResult:
    date_from: date
    date_to: date
    days_processed: int
    processed_campaigns: int
    inserted_rows: int
    updated_rows: int
    skipped_rows: int


def get_campaign_daily_metric_source_inventory() -> dict[str, dict[str, str] | None]:
    return {
        'clicks': {
            'table': 'search_console_daily_metrics',
            'column': 'clicks',
            'timestamp_column': 'metric_date',
        },
        'impressions': {
            'table': 'search_console_daily_metrics',
            'column': 'impressions',
            'timestamp_column': 'metric_date',
        },
        'avg_position': {
            'table': 'search_console_daily_metrics',
            'column': 'avg_position',
            'timestamp_column': 'metric_date',
        },
        'sessions': {
            'table': 'analytics_daily_metrics',
            'column': 'sessions',
            'timestamp_column': 'metric_date',
        },
        'conversions': {
            'table': 'analytics_daily_metrics',
            'column': 'conversions',
            'timestamp_column': 'metric_date',
        },
        'intelligence_score': {
            'table': 'intelligence_scores',
            'column': 'score_value',
            'timestamp_column': 'captured_at',
        },
        'technical_issue_count': {
            'table': 'technical_issues',
            'column': 'id',
            'timestamp_column': 'detected_at',
            'aggregate': 'count',
        },
        'reviews_last_30d': {
            'table': 'review_velocity_snapshots',
            'column': 'reviews_last_30d',
            'timestamp_column': 'captured_at',
        },
    }


def normalize_campaign_daily_metric(metric_input: CampaignDailyMetricInput) -> dict[str, Any]:
    if not metric_input.organization_id:
        raise ValueError('organization_id is required for campaign_daily_metrics normalization')

    payload: dict[str, Any] = {
        'organization_id': metric_input.organization_id,
        'portfolio_id': metric_input.portfolio_id,
        'sub_account_id': metric_input.sub_account_id,
        'campaign_id': metric_input.campaign_id,
        'metric_date': metric_input.metric_date,
        'clicks': metric_input.clicks,
        'impressions': metric_input.impressions,
        'avg_position': metric_input.avg_position,
        'sessions': metric_input.sessions,
        'conversions': metric_input.conversions,
        'technical_issue_count': int(metric_input.technical_issue_count),
        'intelligence_score': metric_input.intelligence_score,
        'reviews_last_30d': int(metric_input.reviews_last_30d),
        'avg_rating_last_30d': metric_input.avg_rating_last_30d,
        'cost': metric_input.cost,
        'revenue': metric_input.revenue,
        'normalization_version': metric_input.normalization_version,
    }
    payload['deterministic_hash'] = _stable_hash(payload)
    return payload


def upsert_campaign_daily_metric(*, db: Session, metric_input: CampaignDailyMetricInput) -> CampaignDailyMetricUpsertResult:
    payload = normalize_campaign_daily_metric(metric_input)
    existing = (
        db.query(CampaignDailyMetric)
        .filter(
            CampaignDailyMetric.campaign_id == metric_input.campaign_id,
            CampaignDailyMetric.metric_date == metric_input.metric_date,
        )
        .first()
    )
    if existing is None:
        row = CampaignDailyMetric(**payload)
        db.add(row)
        db.flush()
        return CampaignDailyMetricUpsertResult(
            inserted=True,
            updated=False,
            skipped=False,
            row_id=row.id,
            deterministic_hash=row.deterministic_hash,
        )

    if existing.deterministic_hash == payload['deterministic_hash']:
        return CampaignDailyMetricUpsertResult(
            inserted=False,
            updated=False,
            skipped=True,
            row_id=existing.id,
            deterministic_hash=existing.deterministic_hash,
        )

    for key, value in payload.items():
        setattr(existing, key, value)
    db.flush()
    return CampaignDailyMetricUpsertResult(
        inserted=False,
        updated=True,
        skipped=False,
        row_id=existing.id,
        deterministic_hash=existing.deterministic_hash,
    )


def rollup_campaign_daily_metrics_for_date(*, db: Session, metric_date: date | str) -> CampaignDailyMetricRollupResult:
    resolved_date = _coerce_date(metric_date)
    day_end = datetime.combine(resolved_date + timedelta(days=1), time.min, tzinfo=UTC)
    campaigns = (
        db.query(Campaign)
        .filter(Campaign.created_at < day_end)
        .order_by(Campaign.created_at.asc(), Campaign.id.asc())
        .all()
    )

    inserted_rows = 0
    updated_rows = 0
    skipped_rows = 0
    for campaign in campaigns:
        metric_input = _build_metric_input_for_campaign(db=db, campaign=campaign, metric_date=resolved_date)
        outcome = upsert_campaign_daily_metric(db=db, metric_input=metric_input)
        inserted_rows += int(outcome.inserted)
        updated_rows += int(outcome.updated)
        skipped_rows += int(outcome.skipped)

    if inserted_rows or updated_rows:
        db.commit()

    return CampaignDailyMetricRollupResult(
        metric_date=resolved_date,
        processed_campaigns=len(campaigns),
        inserted_rows=inserted_rows,
        updated_rows=updated_rows,
        skipped_rows=skipped_rows,
    )


def rollup_campaign_daily_metrics_for_range(
    *,
    db: Session,
    date_from: date | str,
    date_to: date | str,
) -> CampaignDailyMetricRangeRollupResult:
    resolved_start = _coerce_date(date_from)
    resolved_end = _coerce_date(date_to)
    if resolved_end < resolved_start:
        raise ValueError('date_to must be on or after date_from')

    daily_results: list[CampaignDailyMetricRollupResult] = []
    for metric_day in _iter_days(resolved_start, resolved_end):
        daily_results.append(rollup_campaign_daily_metrics_for_date(db=db, metric_date=metric_day))

    return CampaignDailyMetricRangeRollupResult(
        date_from=resolved_start,
        date_to=resolved_end,
        days_processed=len(daily_results),
        processed_campaigns=sum(result.processed_campaigns for result in daily_results),
        inserted_rows=sum(result.inserted_rows for result in daily_results),
        updated_rows=sum(result.updated_rows for result in daily_results),
        skipped_rows=sum(result.skipped_rows for result in daily_results),
    )


def get_latest_campaign_daily_metric(
    db: Session,
    *,
    campaign_id: str,
    on_or_before: date | datetime | None = None,
) -> CampaignDailyMetric | None:
    query = db.query(CampaignDailyMetric).filter(CampaignDailyMetric.campaign_id == campaign_id)
    if on_or_before is not None:
        if isinstance(on_or_before, datetime):
            upper_bound = on_or_before.date()
        else:
            upper_bound = on_or_before
        query = query.filter(CampaignDailyMetric.metric_date <= upper_bound)
    return query.order_by(CampaignDailyMetric.metric_date.desc(), CampaignDailyMetric.id.desc()).first()


def build_campaign_performance_summary_from_metrics(
    db: Session,
    *,
    campaign_id: str,
    date_from: datetime,
    date_to: datetime,
) -> dict[str, Any] | None:
    current_start = date_from.date()
    current_end = date_to.date()
    previous_start, previous_end = _previous_window_bounds(current_start=current_start, current_end=current_end)

    current_rows = _load_campaign_metrics(db=db, campaign_id=campaign_id, date_from=current_start, date_to=current_end)
    previous_rows = _load_campaign_metrics(db=db, campaign_id=campaign_id, date_from=previous_start, date_to=previous_end)

    if not _has_complete_metric_window(current_rows, current_start, current_end):
        return None
    if not _has_complete_metric_window(previous_rows, previous_start, previous_end):
        return None

    current = _aggregate_window(current_rows)
    previous = _aggregate_window(previous_rows)
    visibility_score = _visibility_score(
        impressions=float(current['impressions']),
        avg_position=current['avg_position'],
        ctr=current['ctr'],
    )
    traffic_growth_percent = _percent_growth(
        current_value=float(current['sessions']),
        previous_value=float(previous['sessions']),
    )
    position_delta = _position_delta(
        current_position=current['avg_position'],
        previous_position=previous['avg_position'],
    )
    opportunity_flag = (
        float(current['impressions']) >= OPPORTUNITY_IMPRESSIONS_THRESHOLD
        and float(current['ctr']) <= OPPORTUNITY_CTR_THRESHOLD
    )
    decline_flag = _decline_flag(
        current_sessions=float(current['sessions']),
        previous_sessions=float(previous['sessions']),
    )

    return {
        'campaign_id': campaign_id,
        'date_from': _as_utc(date_from).isoformat(),
        'date_to': _as_utc(date_to).isoformat(),
        'clicks': float(current['clicks']),
        'impressions': float(current['impressions']),
        'ctr': float(current['ctr']),
        'avg_position': current['avg_position'],
        'sessions': float(current['sessions']),
        'conversions': float(current['conversions']),
        'visibility_score': visibility_score,
        'traffic_growth_percent': traffic_growth_percent,
        'position_delta': position_delta,
        'opportunity_flag': opportunity_flag,
        'decline_flag': decline_flag,
    }


def build_campaign_performance_trend_from_metrics(
    db: Session,
    *,
    campaign_id: str,
    date_from: date,
    date_to: date,
    interval: Literal['day', 'week', 'month'],
) -> dict[str, Any] | None:
    rows = _load_campaign_metrics(db=db, campaign_id=campaign_id, date_from=date_from, date_to=date_to)
    if not _has_complete_metric_window(rows, date_from, date_to):
        return None

    by_date = {row.metric_date: row for row in rows}
    points: list[dict[str, Any]] = []
    for period_start, period_end in _iter_periods(date_from=date_from, date_to=date_to, interval=interval):
        bucket_rows = [by_date[day] for day in _iter_days(period_start, period_end)]
        aggregates = _aggregate_window(bucket_rows)
        visibility_score = _visibility_score(
            impressions=float(aggregates['impressions']),
            avg_position=aggregates['avg_position'],
            ctr=float(aggregates['ctr']),
        )
        points.append(
            {
                'period_start': period_start.isoformat(),
                'period_end': period_end.isoformat(),
                'clicks': float(aggregates['clicks']),
                'impressions': float(aggregates['impressions']),
                'ctr': float(aggregates['ctr']),
                'avg_position': aggregates['avg_position'] if aggregates['avg_position'] is not None else 0.0,
                'sessions': float(aggregates['sessions']),
                'conversions': float(aggregates['conversions']),
                'visibility_score': visibility_score,
            }
        )

    return {
        'campaign_id': campaign_id,
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
        'interval': interval,
        'points': points,
    }


def rollup_campaign_metrics_by_scope(
    db: Session,
    *,
    organization_id: str | None = None,
    portfolio_id: str | None = None,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    if organization_id is None and portfolio_id is None:
        raise ValueError('organization_id or portfolio_id is required')

    query = db.query(CampaignDailyMetric).filter(
        CampaignDailyMetric.metric_date >= date_from,
        CampaignDailyMetric.metric_date <= date_to,
    )
    if organization_id is not None:
        query = query.filter(CampaignDailyMetric.organization_id == organization_id)
    if portfolio_id is not None:
        query = query.filter(CampaignDailyMetric.portfolio_id == portfolio_id)

    rows = query.order_by(CampaignDailyMetric.metric_date.asc(), CampaignDailyMetric.id.asc()).all()
    return {
        'organization_id': organization_id,
        'portfolio_id': portfolio_id,
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
        'campaign_count': len({row.campaign_id for row in rows}),
        'days_covered': len({row.metric_date for row in rows}),
        'totals': _aggregate_window(rows),
    }


def _build_metric_input_for_campaign(*, db: Session, campaign: Campaign, metric_date: date) -> CampaignDailyMetricInput:
    if not campaign.organization_id:
        raise ValueError(f'Campaign {campaign.id} is missing organization_id and cannot be rolled up')

    day_start = datetime.combine(metric_date, time.min, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)

    search_console_metric = (
        db.query(SearchConsoleDailyMetric)
        .filter(
            SearchConsoleDailyMetric.campaign_id == campaign.id,
            SearchConsoleDailyMetric.metric_date == metric_date,
        )
        .first()
    )
    analytics_metric = (
        db.query(AnalyticsDailyMetric)
        .filter(
            AnalyticsDailyMetric.campaign_id == campaign.id,
            AnalyticsDailyMetric.metric_date == metric_date,
        )
        .first()
    )
    technical_issue_count = int(
        db.query(func.count(TechnicalIssue.id))
        .filter(
            TechnicalIssue.campaign_id == campaign.id,
            TechnicalIssue.detected_at >= day_start,
            TechnicalIssue.detected_at < day_end,
        )
        .scalar()
        or 0
    )
    intelligence_score = (
        db.query(IntelligenceScore.score_value)
        .filter(
            IntelligenceScore.campaign_id == campaign.id,
            IntelligenceScore.captured_at < day_end,
        )
        .order_by(IntelligenceScore.captured_at.desc(), IntelligenceScore.id.desc())
        .limit(1)
        .scalar()
    )
    review_snapshot = (
        db.query(ReviewVelocitySnapshot)
        .filter(
            ReviewVelocitySnapshot.campaign_id == campaign.id,
            ReviewVelocitySnapshot.captured_at < day_end,
        )
        .order_by(ReviewVelocitySnapshot.captured_at.desc(), ReviewVelocitySnapshot.id.desc())
        .first()
    )

    return CampaignDailyMetricInput(
        organization_id=campaign.organization_id,
        portfolio_id=campaign.portfolio_id,
        sub_account_id=campaign.sub_account_id,
        campaign_id=campaign.id,
        metric_date=metric_date,
        clicks=search_console_metric.clicks if search_console_metric is not None else None,
        impressions=search_console_metric.impressions if search_console_metric is not None else None,
        avg_position=(float(search_console_metric.avg_position) if search_console_metric and search_console_metric.avg_position is not None else None),
        sessions=analytics_metric.sessions if analytics_metric is not None else None,
        conversions=analytics_metric.conversions if analytics_metric is not None else None,
        technical_issue_count=technical_issue_count,
        intelligence_score=float(intelligence_score) if intelligence_score is not None else None,
        reviews_last_30d=review_snapshot.reviews_last_30d if review_snapshot else 0,
        avg_rating_last_30d=review_snapshot.avg_rating_last_30d if review_snapshot else None,
    )


def _load_campaign_metrics(*, db: Session, campaign_id: str, date_from: date, date_to: date) -> list[CampaignDailyMetric]:
    return (
        db.query(CampaignDailyMetric)
        .filter(
            CampaignDailyMetric.campaign_id == campaign_id,
            CampaignDailyMetric.metric_date >= date_from,
            CampaignDailyMetric.metric_date <= date_to,
        )
        .order_by(CampaignDailyMetric.metric_date.asc(), CampaignDailyMetric.id.asc())
        .all()
    )


def _has_complete_metric_window(rows: list[CampaignDailyMetric], date_from: date, date_to: date) -> bool:
    if not rows:
        return False
    expected_dates = {day for day in _iter_days(date_from, date_to)}
    actual_dates = {row.metric_date for row in rows}
    return expected_dates == actual_dates


def _aggregate_window(rows: list[CampaignDailyMetric]) -> dict[str, Any]:
    clicks = sum(int(row.clicks or 0) for row in rows)
    impressions = sum(int(row.impressions or 0) for row in rows)
    sessions = sum(int(row.sessions or 0) for row in rows)
    conversions = sum(int(row.conversions or 0) for row in rows)
    position_weight = 0.0
    position_denominator = 0.0
    fallback_positions: list[float] = []

    for row in rows:
        if row.avg_position is None:
            continue
        if row.impressions is not None and row.impressions > 0:
            position_weight += float(row.avg_position) * float(row.impressions)
            position_denominator += float(row.impressions)
        else:
            fallback_positions.append(float(row.avg_position))

    avg_position: float | None = None
    if position_denominator > 0:
        avg_position = position_weight / position_denominator
    elif fallback_positions:
        avg_position = sum(fallback_positions) / len(fallback_positions)

    ctr = (float(clicks) / float(impressions)) if impressions > 0 else 0.0
    intelligence_values = [float(row.intelligence_score) for row in rows if row.intelligence_score is not None]
    avg_rating_values = [float(row.avg_rating_last_30d) for row in rows if row.avg_rating_last_30d is not None]
    cost_values = [row.cost for row in rows if row.cost is not None]
    revenue_values = [row.revenue for row in rows if row.revenue is not None]

    return {
        'clicks': clicks,
        'impressions': impressions,
        'ctr': ctr,
        'avg_position': avg_position,
        'sessions': sessions,
        'conversions': conversions,
        'technical_issue_count': sum(int(row.technical_issue_count or 0) for row in rows),
        'intelligence_score': (sum(intelligence_values) / len(intelligence_values)) if intelligence_values else None,
        'reviews_last_30d': sum(int(row.reviews_last_30d or 0) for row in rows),
        'avg_rating_last_30d': (sum(avg_rating_values) / len(avg_rating_values)) if avg_rating_values else None,
        'cost': sum(cost_values, Decimal('0.00')) if cost_values else None,
        'revenue': sum(revenue_values, Decimal('0.00')) if revenue_values else None,
    }


def _stable_hash(payload: dict[str, Any]) -> str:
    serialized = {key: _serialize_value(value) for key, value in payload.items()}
    encoded = json.dumps(serialized, sort_keys=True, separators=(',', ':'))
    return sha256(encoded.encode('utf-8')).hexdigest()


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, 'f')
    if isinstance(value, float):
        return format(value, '.15g')
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _coerce_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def _previous_window_bounds(*, current_start: date, current_end: date) -> tuple[date, date]:
    span_days = (current_end - current_start).days + 1
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=span_days - 1)
    return previous_start, previous_end


def _iter_days(start: date, end: date) -> list[date]:
    days: list[date] = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _iter_periods(*, date_from: date, date_to: date, interval: Literal['day', 'week', 'month']) -> list[tuple[date, date]]:
    periods: list[tuple[date, date]] = []
    cursor = date_from
    while cursor <= date_to:
        if interval == 'day':
            period_end = cursor
        elif interval == 'week':
            period_end = min(date_to, cursor + timedelta(days=6))
        else:
            next_month = _first_day_of_next_month(cursor)
            period_end = min(date_to, next_month - timedelta(days=1))
        periods.append((cursor, period_end))
        cursor = period_end + timedelta(days=1)
    return periods


def _first_day_of_next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _visibility_score(*, impressions: float, avg_position: float | None, ctr: float) -> float:
    impression_component = min(50.0, log10(max(impressions, 1.0)) * 12.5)
    ctr_component = min(30.0, max(0.0, ctr) * 300.0)
    position_component = 0.0
    if avg_position is not None and avg_position > 0:
        normalized = max(0.0, 1.0 - min(avg_position, 100.0) / 100.0)
        position_component = normalized * 20.0
    return round(impression_component + ctr_component + position_component, 2)


def _percent_growth(*, current_value: float, previous_value: float) -> float | None:
    if previous_value <= 0:
        if current_value <= 0:
            return 0.0
        return None
    return round(((current_value - previous_value) / previous_value) * 100.0, 2)


def _position_delta(*, current_position: float | None, previous_position: float | None) -> float | None:
    if current_position is None or previous_position is None:
        return None
    return round(previous_position - current_position, 2)


def _decline_flag(*, current_sessions: float, previous_sessions: float) -> bool:
    if previous_sessions <= 0:
        return False
    drop_percent = ((previous_sessions - current_sessions) / previous_sessions) * 100.0
    return drop_percent >= DECLINE_SESSIONS_DROP_THRESHOLD_PERCENT
