from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.intelligence.pattern_engine import discover_cohort_patterns, discover_patterns_for_campaign
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.digital_twin_simulation import DigitalTwinSimulation
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

        simulations_run = _count_in_range(
            session,
            DigitalTwinSimulation,
            DigitalTwinSimulation.created_at,
            [DigitalTwinSimulation.campaign_id == campaign_id],
            day_start,
            day_end,
        )
        avg_predicted_rank_delta = (
            session.query(func.avg(DigitalTwinSimulation.predicted_rank_delta))
            .filter(
                DigitalTwinSimulation.campaign_id == campaign_id,
                DigitalTwinSimulation.created_at >= day_start,
                DigitalTwinSimulation.created_at < day_end,
            )
            .scalar()
        )
        avg_confidence = (
            session.query(func.avg(DigitalTwinSimulation.confidence))
            .filter(
                DigitalTwinSimulation.campaign_id == campaign_id,
                DigitalTwinSimulation.created_at >= day_start,
                DigitalTwinSimulation.created_at < day_end,
            )
            .scalar()
        )
        selected_count = _count_in_range(
            session,
            DigitalTwinSimulation,
            DigitalTwinSimulation.created_at,
            [DigitalTwinSimulation.campaign_id == campaign_id, DigitalTwinSimulation.selected_strategy.is_(True)],
            day_start,
            day_end,
        )
        optimizer_selection_rate = _safe_div(selected_count, max(simulations_run, 1))

        accuracy = _compute_prediction_accuracy(
            session,
            day_start=day_start,
            day_end=day_end,
            campaign_id=campaign_id,
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
        snapshot.simulations_run = simulations_run
        snapshot.avg_predicted_rank_delta = round(float(avg_predicted_rank_delta or 0.0), 6)
        snapshot.avg_confidence = round(float(avg_confidence or 0.0), 6)
        snapshot.optimizer_selection_rate = round(float(optimizer_selection_rate), 6)
        snapshot.avg_prediction_error_rank = round(float(accuracy['avg_prediction_error_rank']), 6)
        snapshot.avg_prediction_error_traffic = round(float(accuracy['avg_prediction_error_traffic']), 6)
        snapshot.prediction_accuracy_score = round(float(accuracy['prediction_accuracy_score']), 6)
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
        day_start, day_end = _day_bounds(target_date)

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
                'simulations_run': 0,
                'recommendation_success_rate': 0.0,
                'execution_success_rate': 0.0,
                'pattern_discovery_rate': 0.0,
                'learning_velocity': 0.0,
                'average_outcome_delta': 0.0,
                'avg_predicted_rank_delta': 0.0,
                'avg_confidence': 0.0,
                'optimizer_selection_rate': 0.0,
                'avg_prediction_error_rank': 0.0,
                'avg_prediction_error_traffic': 0.0,
                'prediction_accuracy_score': 0.0,
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
            'simulations_run': sum(row.simulations_run for row in rows),
        }

        weighted_predicted_rank_total = sum(row.avg_predicted_rank_delta * row.simulations_run for row in rows)
        weighted_confidence_total = sum(row.avg_confidence * row.simulations_run for row in rows)
        weighted_selection_total = sum(row.optimizer_selection_rate * row.simulations_run for row in rows)

        avg_predicted_rank_delta = _safe_div(weighted_predicted_rank_total, max(totals['simulations_run'], 1))
        avg_confidence = _safe_div(weighted_confidence_total, max(totals['simulations_run'], 1))
        optimizer_selection_rate = _safe_div(weighted_selection_total, max(totals['simulations_run'], 1))

        total_outcomes = totals['positive_outcomes'] + totals['negative_outcomes']
        recommendation_success_rate = _safe_div(totals['positive_outcomes'], max(total_outcomes, 1))
        execution_success_rate = _safe_div(totals['positive_outcomes'], max(totals['executions_run'], 1))
        pattern_discovery_rate = _safe_div(totals['patterns_detected'], max(totals['features_computed'], 1))
        learning_velocity = _safe_div(totals['policy_updates_applied'], max(len(rows), 1))

        avg_delta = (
            session.query(func.avg(RecommendationOutcome.delta))
            .filter(RecommendationOutcome.measured_at >= day_start, RecommendationOutcome.measured_at < day_end)
            .scalar()
        )

        accuracy = _compute_prediction_accuracy(session, day_start=day_start, day_end=day_end, campaign_id=None)

        return {
            'campaigns_tracked': len(rows),
            **totals,
            'recommendation_success_rate': round(recommendation_success_rate, 6),
            'execution_success_rate': round(execution_success_rate, 6),
            'pattern_discovery_rate': round(pattern_discovery_rate, 6),
            'learning_velocity': round(learning_velocity, 6),
            'average_outcome_delta': round(float(avg_delta or 0.0), 6),
            'avg_predicted_rank_delta': round(avg_predicted_rank_delta, 6),
            'avg_confidence': round(avg_confidence, 6),
            'optimizer_selection_rate': round(optimizer_selection_rate, 6),
            'avg_prediction_error_rank': round(float(accuracy['avg_prediction_error_rank']), 6),
            'avg_prediction_error_traffic': round(float(accuracy['avg_prediction_error_traffic']), 6),
            'prediction_accuracy_score': round(float(accuracy['prediction_accuracy_score']), 6),
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


def _compute_prediction_accuracy(
    db: Session,
    *,
    day_start: datetime,
    day_end: datetime,
    campaign_id: str | None,
) -> dict[str, float]:
    query = (
        db.query(
            RecommendationOutcome.delta,
            DigitalTwinSimulation.predicted_rank_delta,
            DigitalTwinSimulation.predicted_traffic_delta,
        )
        .join(DigitalTwinSimulation, RecommendationOutcome.simulation_id == DigitalTwinSimulation.id)
        .filter(
            RecommendationOutcome.simulation_id.is_not(None),
            RecommendationOutcome.measured_at >= day_start,
            RecommendationOutcome.measured_at < day_end,
        )
    )
    if campaign_id is not None:
        query = query.filter(RecommendationOutcome.campaign_id == campaign_id)

    rows = query.all()
    if not rows:
        return {
            'avg_prediction_error_rank': 0.0,
            'avg_prediction_error_traffic': 0.0,
            'prediction_accuracy_score': 0.0,
        }

    total_rank_error = 0.0
    total_traffic_error = 0.0
    total_accuracy = 0.0

    for row in rows:
        actual_rank_delta = float(row.delta or 0.0)
        actual_traffic_delta = float(row.delta or 0.0)
        predicted_rank_delta = float(row.predicted_rank_delta or 0.0)
        predicted_traffic_delta = float(row.predicted_traffic_delta or 0.0)

        rank_error = abs(predicted_rank_delta - actual_rank_delta)
        traffic_error = abs(predicted_traffic_delta - actual_traffic_delta)

        norm_rank = rank_error / (abs(actual_rank_delta) + 1.0)
        norm_traffic = traffic_error / (abs(actual_traffic_delta) + 1.0)
        accuracy = max(0.0, 1.0 - ((norm_rank + norm_traffic) / 2.0))

        total_rank_error += rank_error
        total_traffic_error += traffic_error
        total_accuracy += accuracy

    count = float(len(rows))
    return {
        'avg_prediction_error_rank': total_rank_error / count,
        'avg_prediction_error_traffic': total_traffic_error / count,
        'prediction_accuracy_score': total_accuracy / count,
    }


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
