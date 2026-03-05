from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.intelligence.pattern_engine import discover_cohort_patterns, discover_patterns_for_campaign
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.intelligence import StrategyRecommendation
from app.models.intelligence_metrics_snapshot import IntelligenceMetricsSnapshot
from app.models.recommendation_execution import RecommendationExecution
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.temporal import TemporalSignalSnapshot


def compute_campaign_metrics(
    campaign_id: str,
    db: Session | None = None,
    *,
    metric_date: date | None = None,
) -> IntelligenceMetricsSnapshot:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        target_date = metric_date or datetime.now(UTC).date()
        day_start, day_end = _day_bounds(target_date)

        campaign = session.get(Campaign, campaign_id)
        if campaign is None:
            raise ValueError('campaign not found')

        signals_processed = _count_in_range(
            session,
            TemporalSignalSnapshot,
            TemporalSignalSnapshot.observed_at,
            [TemporalSignalSnapshot.campaign_id == campaign_id],
            day_start,
            day_end,
        )
        features_computed = _count_in_range(
            session,
            TemporalSignalSnapshot,
            TemporalSignalSnapshot.observed_at,
            [TemporalSignalSnapshot.campaign_id == campaign_id, TemporalSignalSnapshot.source == 'feature_store_v1'],
            day_start,
            day_end,
        )

        patterns_detected = len(discover_patterns_for_campaign(campaign_id, session, persist_features=False)) + len(
            discover_cohort_patterns(session, campaign_id=campaign_id)
        )

        recommendations_generated = _count_in_range(
            session,
            StrategyRecommendation,
            StrategyRecommendation.created_at,
            [StrategyRecommendation.campaign_id == campaign_id],
            day_start,
            day_end,
        )
        executions_run = _count_in_range(
            session,
            RecommendationExecution,
            RecommendationExecution.executed_at,
            [RecommendationExecution.campaign_id == campaign_id, RecommendationExecution.executed_at.is_not(None)],
            day_start,
            day_end,
        )
        positive_outcomes = _count_in_range(
            session,
            RecommendationOutcome,
            RecommendationOutcome.measured_at,
            [RecommendationOutcome.campaign_id == campaign_id, RecommendationOutcome.delta > 0],
            day_start,
            day_end,
        )
        negative_outcomes = _count_in_range(
            session,
            RecommendationOutcome,
            RecommendationOutcome.measured_at,
            [RecommendationOutcome.campaign_id == campaign_id, RecommendationOutcome.delta < 0],
            day_start,
            day_end,
        )
        policy_updates_applied = _count_in_range(
            session,
            AuditLog,
            AuditLog.created_at,
            [AuditLog.event_type == 'recommendation.outcome_recorded', AuditLog.payload_json.like(f'%{campaign_id}%')],
            day_start,
            day_end,
        )

        snapshot = (
            session.query(IntelligenceMetricsSnapshot)
            .filter(
                IntelligenceMetricsSnapshot.campaign_id == campaign_id,
                IntelligenceMetricsSnapshot.metric_date == target_date,
            )
            .first()
        )
        if snapshot is None:
            snapshot = IntelligenceMetricsSnapshot(campaign_id=campaign_id, metric_date=target_date)
            session.add(snapshot)

        snapshot.signals_processed = signals_processed
        snapshot.features_computed = features_computed
        snapshot.patterns_detected = patterns_detected
        snapshot.recommendations_generated = recommendations_generated
        snapshot.executions_run = executions_run
        snapshot.positive_outcomes = positive_outcomes
        snapshot.negative_outcomes = negative_outcomes
        snapshot.policy_updates_applied = policy_updates_applied
        snapshot.created_at = datetime.now(UTC)

        session.flush()
        if owns_session:
            session.commit()
            session.refresh(snapshot)
        return snapshot
    finally:
        if owns_session:
            session.close()


def compute_system_metrics(db: Session | None = None, *, metric_date: date | None = None) -> dict[str, float | int]:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        target_date = metric_date or datetime.now(UTC).date()
        for (campaign_id,) in session.query(Campaign.id).all():
            compute_campaign_metrics(campaign_id, db=session, metric_date=target_date)

        rows = session.query(IntelligenceMetricsSnapshot).filter(IntelligenceMetricsSnapshot.metric_date == target_date).all()
        if not rows:
            return {
                'campaigns_tracked': 0,
                'signals_processed': 0,
                'features_computed': 0,
                'patterns_detected': 0,
                'recommendations_generated': 0,
                'executions_run': 0,
                'positive_outcomes': 0,
                'negative_outcomes': 0,
                'policy_updates_applied': 0,
                'recommendation_success_rate': 0.0,
                'execution_success_rate': 0.0,
                'pattern_discovery_rate': 0.0,
                'learning_velocity': 0.0,
                'average_outcome_delta': 0.0,
            }

        totals = {
            'signals_processed': sum(row.signals_processed for row in rows),
            'features_computed': sum(row.features_computed for row in rows),
            'patterns_detected': sum(row.patterns_detected for row in rows),
            'recommendations_generated': sum(row.recommendations_generated for row in rows),
            'executions_run': sum(row.executions_run for row in rows),
            'positive_outcomes': sum(row.positive_outcomes for row in rows),
            'negative_outcomes': sum(row.negative_outcomes for row in rows),
            'policy_updates_applied': sum(row.policy_updates_applied for row in rows),
        }

        total_outcomes = totals['positive_outcomes'] + totals['negative_outcomes']
        recommendation_success_rate = _safe_div(totals['positive_outcomes'], max(total_outcomes, 1))
        execution_success_rate = _safe_div(totals['positive_outcomes'], max(totals['executions_run'], 1))
        pattern_discovery_rate = _safe_div(totals['patterns_detected'], max(totals['features_computed'], 1))
        learning_velocity = _safe_div(totals['policy_updates_applied'], max(len(rows), 1))

        day_start, day_end = _day_bounds(target_date)
        avg_delta = (
            session.query(func.avg(RecommendationOutcome.delta))
            .filter(RecommendationOutcome.measured_at >= day_start, RecommendationOutcome.measured_at < day_end)
            .scalar()
        )

        return {
            'campaigns_tracked': len(rows),
            **totals,
            'recommendation_success_rate': round(recommendation_success_rate, 6),
            'execution_success_rate': round(execution_success_rate, 6),
            'pattern_discovery_rate': round(pattern_discovery_rate, 6),
            'learning_velocity': round(learning_velocity, 6),
            'average_outcome_delta': round(float(avg_delta or 0.0), 6),
        }
    finally:
        if owns_session:
            session.close()


def compute_campaign_trends(campaign_id: str, db: Session | None = None, *, days: int = 30) -> dict[str, object]:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        window_days = max(2, int(days))
        today = datetime.now(UTC).date()
        start_date = today - timedelta(days=window_days - 1)

        rows = (
            session.query(IntelligenceMetricsSnapshot)
            .filter(
                IntelligenceMetricsSnapshot.campaign_id == campaign_id,
                IntelligenceMetricsSnapshot.metric_date >= start_date,
                IntelligenceMetricsSnapshot.metric_date <= today,
            )
            .order_by(IntelligenceMetricsSnapshot.metric_date.asc())
            .all()
        )

        success_rate_over_time: list[dict[str, object]] = []
        for row in rows:
            outcomes = row.positive_outcomes + row.negative_outcomes
            success_rate_over_time.append(
                {
                    'metric_date': row.metric_date.isoformat(),
                    'recommendation_success_rate': round(_safe_div(row.positive_outcomes, max(outcomes, 1)), 6),
                    'execution_success_rate': round(_safe_div(row.positive_outcomes, max(row.executions_run, 1)), 6),
                }
            )

        pattern_growth_rate = 0.0
        if len(rows) >= 2:
            first = rows[0].patterns_detected
            last = rows[-1].patterns_detected
            pattern_growth_rate = _safe_div(last - first, max(first, 1))

        policy_total = sum(row.policy_updates_applied for row in rows)
        policy_weight_changes = {
            'policy_updates_window_total': policy_total,
            'policy_updates_daily_avg': round(_safe_div(policy_total, max(len(rows), 1)), 6),
        }

        avg_delta = (
            session.query(func.avg(RecommendationOutcome.delta))
            .filter(
                RecommendationOutcome.campaign_id == campaign_id,
                RecommendationOutcome.measured_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=UTC),
                RecommendationOutcome.measured_at < datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=UTC),
            )
            .scalar()
        )

        total_patterns = sum(row.patterns_detected for row in rows)
        total_features = sum(row.features_computed for row in rows)

        return {
            'campaign_id': campaign_id,
            'window_days': window_days,
            'success_rate_over_time': success_rate_over_time,
            'pattern_growth_rate': round(pattern_growth_rate, 6),
            'policy_weight_changes': policy_weight_changes,
            'average_outcome_delta': round(float(avg_delta or 0.0), 6),
            'pattern_discovery_rate': round(_safe_div(total_patterns, max(total_features, 1)), 6),
            'learning_velocity': round(_safe_div(policy_total, max(len(rows), 1)), 6),
            'campaign_improvement_trend': round(float(avg_delta or 0.0), 6),
        }
    finally:
        if owns_session:
            session.close()


def _day_bounds(metric_date: date) -> tuple[datetime, datetime]:
    day_start = datetime(metric_date.year, metric_date.month, metric_date.day, tzinfo=UTC)
    return day_start, day_start + timedelta(days=1)


def _count_in_range(db: Session, model: type, timestamp_column, filters: list, day_start: datetime, day_end: datetime) -> int:
    query = db.query(model)
    for item in filters:
        query = query.filter(item)
    query = query.filter(timestamp_column >= day_start, timestamp_column < day_end)
    return int(query.count())


def _safe_div(numerator: float | int, denominator: float | int) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


def compute_system_trends(db: Session | None = None, *, days: int = 30) -> dict[str, object]:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        window_days = max(2, int(days))
        today = datetime.now(UTC).date()
        start_date = today - timedelta(days=window_days - 1)

        rows = (
            session.query(IntelligenceMetricsSnapshot)
            .filter(
                IntelligenceMetricsSnapshot.metric_date >= start_date,
                IntelligenceMetricsSnapshot.metric_date <= today,
            )
            .all()
        )

        grouped: dict[str, dict[str, int]] = {}
        for row in rows:
            key = row.metric_date.isoformat()
            bucket = grouped.setdefault(
                key,
                {
                    'positive_outcomes': 0,
                    'negative_outcomes': 0,
                    'executions_run': 0,
                    'patterns_detected': 0,
                    'features_computed': 0,
                    'policy_updates_applied': 0,
                },
            )
            bucket['positive_outcomes'] += row.positive_outcomes
            bucket['negative_outcomes'] += row.negative_outcomes
            bucket['executions_run'] += row.executions_run
            bucket['patterns_detected'] += row.patterns_detected
            bucket['features_computed'] += row.features_computed
            bucket['policy_updates_applied'] += row.policy_updates_applied

        success_rate_over_time: list[dict[str, object]] = []
        ordered_keys = sorted(grouped.keys())
        for key in ordered_keys:
            bucket = grouped[key]
            outcomes = bucket['positive_outcomes'] + bucket['negative_outcomes']
            success_rate_over_time.append(
                {
                    'metric_date': key,
                    'recommendation_success_rate': round(_safe_div(bucket['positive_outcomes'], max(outcomes, 1)), 6),
                    'execution_success_rate': round(_safe_div(bucket['positive_outcomes'], max(bucket['executions_run'], 1)), 6),
                }
            )

        if len(ordered_keys) >= 2:
            first_patterns = grouped[ordered_keys[0]]['patterns_detected']
            last_patterns = grouped[ordered_keys[-1]]['patterns_detected']
            pattern_growth_rate = _safe_div(last_patterns - first_patterns, max(first_patterns, 1))
        else:
            pattern_growth_rate = 0.0

        total_policy_updates = sum(item['policy_updates_applied'] for item in grouped.values())

        avg_delta = (
            session.query(func.avg(RecommendationOutcome.delta))
            .filter(
                RecommendationOutcome.measured_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=UTC),
                RecommendationOutcome.measured_at < datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=UTC),
            )
            .scalar()
        )

        total_patterns = sum(item['patterns_detected'] for item in grouped.values())
        total_features = sum(item['features_computed'] for item in grouped.values())

        return {
            'campaign_id': None,
            'window_days': window_days,
            'success_rate_over_time': success_rate_over_time,
            'pattern_growth_rate': round(pattern_growth_rate, 6),
            'policy_weight_changes': {
                'policy_updates_window_total': total_policy_updates,
                'policy_updates_daily_avg': round(_safe_div(total_policy_updates, max(len(ordered_keys), 1)), 6),
            },
            'average_outcome_delta': round(float(avg_delta or 0.0), 6),
            'pattern_discovery_rate': round(_safe_div(total_patterns, max(total_features, 1)), 6),
            'learning_velocity': round(_safe_div(total_policy_updates, max(len(ordered_keys), 1)), 6),
            'campaign_improvement_trend': round(float(avg_delta or 0.0), 6),
        }
    finally:
        if owns_session:
            session.close()
