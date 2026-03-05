from __future__ import annotations

from statistics import mean, pvariance
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.digital_twin.models.model_registry import get_model_parameters, update_model_parameters
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.strategy_cohort_pattern import StrategyCohortPattern
from app.models.temporal import TemporalSignalSnapshot


def train_prediction_models(db: Session) -> dict[str, Any]:
    outcomes = db.query(RecommendationOutcome).all()
    daily_metrics = db.query(CampaignDailyMetric).all()
    cohort_patterns = db.query(StrategyCohortPattern).all()
    snapshots = db.query(TemporalSignalSnapshot).all()

    outcome_deltas = [float(row.delta) for row in outcomes]
    avg_outcome_delta = mean(outcome_deltas) if outcome_deltas else 0.0
    outcome_variance = pvariance(outcome_deltas) if len(outcome_deltas) > 1 else 0.0

    technical_issue_counts = [int(row.technical_issue_count or 0) for row in daily_metrics]
    avg_technical_issue_count = mean(technical_issue_counts) if technical_issue_counts else 0.0

    avg_rank_values = [float(row.avg_position) for row in daily_metrics if row.avg_position is not None]
    avg_rank_baseline = mean(avg_rank_values) if avg_rank_values else 10.0

    pattern_strengths = [float(row.pattern_strength) for row in cohort_patterns]
    pattern_confidences = [float(row.confidence) for row in cohort_patterns]
    avg_pattern_strength = mean(pattern_strengths) if pattern_strengths else 0.0
    avg_pattern_confidence = mean(pattern_confidences) if pattern_confidences else 0.0

    momentum_values = [
        float(row.metric_value)
        for row in snapshots
        if str(row.metric_name) in {'ranking_velocity', 'momentum_score'}
    ]
    avg_momentum = mean(momentum_values) if momentum_values else 0.0

    coefficients = {
        'internal_links_added': round(_bounded(0.15 + avg_pattern_strength * 0.15 + max(avg_outcome_delta, 0.0) * 0.03, 0.05, 0.5), 6),
        'pages_added': round(_bounded(0.30 + avg_pattern_confidence * 0.2 + max(avg_outcome_delta, 0.0) * 0.04, 0.1, 0.7), 6),
        'issues_fixed': round(_bounded(0.20 + (1.0 / (1.0 + avg_technical_issue_count)) * 0.25, 0.05, 0.6), 6),
        'momentum_score': round(_bounded(0.10 + max(avg_momentum, 0.0) * 0.05, 0.05, 0.3), 6),
        'cohort_pattern_strength': round(_bounded(0.05 + avg_pattern_strength * 0.2, 0.02, 0.4), 6),
        'avg_rank_bias': round(_bounded(-avg_rank_baseline * 0.001, -0.08, 0.0), 6),
        'technical_issue_penalty': round(_bounded(avg_technical_issue_count * 0.0005, 0.0, 0.1), 6),
    }

    traffic_factor = round(_bounded(0.07 + max(avg_outcome_delta, 0.0) * 0.002, 0.03, 0.2), 6)

    confidence_parameters = {
        'base': round(_bounded(0.40 + avg_pattern_confidence * 0.05, 0.30, 0.60), 6),
        'pattern_weight': round(_bounded(0.20 + avg_pattern_confidence * 0.10, 0.10, 0.35), 6),
        'sample_weight': round(_bounded(0.25 + min(len(outcomes), 50) / 500.0, 0.20, 0.35), 6),
        'cohort_weight': round(_bounded(0.08 + avg_pattern_strength * 0.08, 0.05, 0.20), 6),
        'variance_weight': round(_bounded(0.06 + (1.0 / (1.0 + outcome_variance)) * 0.08, 0.04, 0.20), 6),
        'sample_size_norm': float(max(5, min(100, len(outcomes) if outcomes else 20))),
        'historical_variance_baseline': round(float(outcome_variance), 6),
    }

    version_suffix = f'{len(outcomes)}_{len(daily_metrics)}_{len(cohort_patterns)}_{len(snapshots)}'
    updates = {
        'rank_model_version': f'v1-{version_suffix}',
        'traffic_model_version': f'v1-{version_suffix}',
        'confidence_model_version': f'v1-{version_suffix}',
        'coefficients': coefficients,
        'traffic_factor': traffic_factor,
        'confidence_parameters': confidence_parameters,
    }
    previous_registry = get_model_parameters()
    updated_registry = update_model_parameters(updates)

    return {
        'trained': True,
        'samples': {
            'recommendation_outcomes': len(outcomes),
            'campaign_daily_metrics': len(daily_metrics),
            'strategy_cohort_patterns': len(cohort_patterns),
            'temporal_signal_snapshots': len(snapshots),
        },
        'coefficients': coefficients,
        'traffic_factor': traffic_factor,
        'confidence_parameters': confidence_parameters,
        'model_registry': updated_registry,
        'previous_registry': previous_registry,
    }


def _bounded(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, float(value)))
