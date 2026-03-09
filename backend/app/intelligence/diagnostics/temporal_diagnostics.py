from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.temporal import TemporalSignalSnapshot, TemporalSignalType
from app.services.strategy_engine import thresholds
from app.services.strategy_engine.competitive_trajectory import classify_relative_momentum, compute_relative_momentum_score
from app.services.strategy_engine.schemas import DiagnosticResult, Evidence, StrategyWindow
from app.services.strategy_engine.temporal_math import compute_acceleration, compute_slope, compute_trend_strength, compute_volatility


def _series(
    db: Session,
    campaign_id: str,
    signal_type: TemporalSignalType,
    metric_name: str,
    date_from: datetime,
    date_to: datetime,
) -> tuple[list[float], list[datetime]]:
    rows = (
        db.query(TemporalSignalSnapshot)
        .filter(
            TemporalSignalSnapshot.campaign_id == campaign_id,
            TemporalSignalSnapshot.signal_type == signal_type,
            TemporalSignalSnapshot.metric_name == metric_name,
            TemporalSignalSnapshot.observed_at >= date_from,
            TemporalSignalSnapshot.observed_at <= date_to,
        )
        .order_by(TemporalSignalSnapshot.observed_at.asc(), TemporalSignalSnapshot.id.asc())
        .all()
    )
    values = [float(item.metric_value) for item in rows]
    timestamps = [item.observed_at for item in rows]
    return values, timestamps


def rank_momentum_diagnostic(db: Session, campaign_id: str, window: StrategyWindow, window_reference: str) -> list[DiagnosticResult]:
    values, timestamps = _series(
        db,
        campaign_id=campaign_id,
        signal_type=TemporalSignalType.RANK,
        metric_name='avg_position',
        date_from=window.date_from,
        date_to=window.date_to,
    )
    if len(values) < 3:
        return []

    slope = compute_slope(values, timestamps)
    trend_strength = compute_trend_strength(values)
    if slope < 0.05:
        return []

    return [
        DiagnosticResult(
            scenario_id='rank_negative_momentum',
            confidence=thresholds.DIAGNOSTIC_CONFIDENCE_MEDIUM,
            signal_magnitude=thresholds.MEDIUM_PRIORITY_SIGNAL_MAGNITUDE,
            evidence=[
                Evidence(
                    signal_name='rank_slope',
                    signal_value=slope,
                    threshold_reference='TEMPORAL_RANK_SLOPE_THRESHOLD',
                    comparator='>=',
                    comparative_value=0.05,
                    window_reference=window_reference,
                ),
                Evidence(
                    signal_name='rank_trend_strength',
                    signal_value=trend_strength,
                    threshold_reference='TEMPORAL_TREND_STRENGTH_REFERENCE',
                    comparator='>=',
                    comparative_value=0.2,
                    window_reference=window_reference,
                ),
            ],
        )
    ]


def review_velocity_diagnostic(db: Session, campaign_id: str, window: StrategyWindow, window_reference: str) -> list[DiagnosticResult]:
    values, timestamps = _series(
        db,
        campaign_id=campaign_id,
        signal_type=TemporalSignalType.REVIEW,
        metric_name='reviews_last_30d',
        date_from=window.date_from,
        date_to=window.date_to,
    )
    if len(values) < 3:
        return []

    slope = compute_slope(values, timestamps)
    acceleration = compute_acceleration(values, timestamps)
    if slope >= 0:
        return []

    return [
        DiagnosticResult(
            scenario_id='review_velocity_declining',
            confidence=thresholds.DIAGNOSTIC_CONFIDENCE_MEDIUM,
            signal_magnitude=thresholds.MEDIUM_PRIORITY_SIGNAL_MAGNITUDE,
            evidence=[
                Evidence(
                    signal_name='review_velocity_slope',
                    signal_value=slope,
                    threshold_reference='TEMPORAL_REVIEW_SLOPE_THRESHOLD',
                    comparator='<',
                    comparative_value=0.0,
                    window_reference=window_reference,
                ),
                Evidence(
                    signal_name='review_velocity_acceleration',
                    signal_value=acceleration,
                    threshold_reference='TEMPORAL_REVIEW_ACCEL_REFERENCE',
                    comparator='<=',
                    comparative_value=0.0,
                    window_reference=window_reference,
                ),
            ],
        )
    ]


def competitor_trajectory_diagnostic(
    db: Session,
    campaign_id: str,
    window: StrategyWindow,
    window_reference: str,
) -> list[DiagnosticResult]:
    our_values, our_timestamps = _series(
        db,
        campaign_id=campaign_id,
        signal_type=TemporalSignalType.COMPETITOR,
        metric_name='our_share_of_voice',
        date_from=window.date_from,
        date_to=window.date_to,
    )
    competitor_values, competitor_timestamps = _series(
        db,
        campaign_id=campaign_id,
        signal_type=TemporalSignalType.COMPETITOR,
        metric_name='competitor_share_of_voice',
        date_from=window.date_from,
        date_to=window.date_to,
    )
    if len(our_values) < 3 or len(competitor_values) < 3:
        return []

    our_slope = compute_slope(our_values, our_timestamps)
    competitor_slope = compute_slope(competitor_values, competitor_timestamps)
    volatility = max(compute_volatility(our_values), compute_volatility(competitor_values))
    relative_score = compute_relative_momentum_score(our_slope, competitor_slope, impact_weight=1.0)
    classification = classify_relative_momentum(
        our_slope=our_slope,
        competitor_slope=competitor_slope,
        volatility=volatility,
        impact_weight=1.0,
    )

    if classification == 'stagnating':
        return []

    scenario_id = 'competitive_momentum_volatile' if classification == 'volatile' else 'competitive_momentum_gap'
    return [
        DiagnosticResult(
            scenario_id=scenario_id,
            confidence=thresholds.DIAGNOSTIC_CONFIDENCE_MEDIUM,
            signal_magnitude=thresholds.MEDIUM_PRIORITY_SIGNAL_MAGNITUDE,
            evidence=[
                Evidence(
                    signal_name='relative_momentum_score',
                    signal_value=relative_score,
                    threshold_reference='RELATIVE_MOMENTUM_SCORE',
                    comparator='classified_as',
                    comparative_value=None,
                    window_reference=f'{window_reference}:{classification}',
                ),
                Evidence(
                    signal_name='momentum_volatility',
                    signal_value=volatility,
                    threshold_reference='VOLATILITY_THRESHOLD',
                    comparator='>=',
                    comparative_value=0.75,
                    window_reference=window_reference,
                ),
            ],
        )
    ]


def content_velocity_diagnostic(db: Session, campaign_id: str, window: StrategyWindow, window_reference: str) -> list[DiagnosticResult]:
    values, timestamps = _series(
        db,
        campaign_id=campaign_id,
        signal_type=TemporalSignalType.CONTENT,
        metric_name='published_assets_count',
        date_from=window.date_from,
        date_to=window.date_to,
    )
    if len(values) < 3:
        return []

    slope = compute_slope(values, timestamps)
    volatility = compute_volatility(values)
    if slope >= 0:
        return []

    return [
        DiagnosticResult(
            scenario_id='content_velocity_decline',
            confidence=thresholds.DIAGNOSTIC_CONFIDENCE_MEDIUM,
            signal_magnitude=thresholds.MEDIUM_PRIORITY_SIGNAL_MAGNITUDE,
            evidence=[
                Evidence(
                    signal_name='content_velocity_slope',
                    signal_value=slope,
                    threshold_reference='TEMPORAL_CONTENT_SLOPE_THRESHOLD',
                    comparator='<',
                    comparative_value=0.0,
                    window_reference=window_reference,
                ),
                Evidence(
                    signal_name='content_velocity_volatility',
                    signal_value=volatility,
                    threshold_reference='TEMPORAL_CONTENT_VOLATILITY_REF',
                    comparator='>=',
                    comparative_value=0.0,
                    window_reference=window_reference,
                ),
            ],
        )
    ]


def run_temporal_diagnostics(
    db: Session,
    campaign_id: str,
    window: StrategyWindow,
    window_reference: str,
    tier: str,
) -> list[DiagnosticResult]:
    results: list[DiagnosticResult] = []
    results.extend(rank_momentum_diagnostic(db, campaign_id=campaign_id, window=window, window_reference=window_reference))
    results.extend(review_velocity_diagnostic(db, campaign_id=campaign_id, window=window, window_reference=window_reference))
    results.extend(content_velocity_diagnostic(db, campaign_id=campaign_id, window=window, window_reference=window_reference))
    if tier == 'enterprise':
        results.extend(
            competitor_trajectory_diagnostic(db, campaign_id=campaign_id, window=window, window_reference=window_reference)
        )
    return results
