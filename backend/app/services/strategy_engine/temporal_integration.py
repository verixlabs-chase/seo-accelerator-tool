from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.temporal import MomentumMetric, StrategyPhaseHistory, TemporalSignalSnapshot, TemporalSignalType
from app.services.strategy_engine.profile import StrategyEngineProfile
from app.services.strategy_engine.schemas import StrategyWindow
from app.services.strategy_engine.temporal_math import (
    compute_acceleration,
    compute_slope,
    compute_trend_strength,
    compute_volatility,
)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _series(db: Session, campaign_id: str, window: StrategyWindow, profile: StrategyEngineProfile) -> tuple[list[float], list[datetime]]:
    from datetime import timedelta

    date_from = max(window.date_from, window.date_to - timedelta(days=profile.trend_window_days))
    rows = (
        db.query(TemporalSignalSnapshot)
        .filter(
            TemporalSignalSnapshot.campaign_id == campaign_id,
            TemporalSignalSnapshot.signal_type == TemporalSignalType.RANK,
            TemporalSignalSnapshot.metric_name == 'avg_position',
            TemporalSignalSnapshot.observed_at >= date_from,
            TemporalSignalSnapshot.observed_at <= window.date_to,
        )
        .order_by(TemporalSignalSnapshot.observed_at.asc(), TemporalSignalSnapshot.id.asc())
        .all()
    )
    return [float(row.metric_value) for row in rows], [row.observed_at for row in rows]


def _trend_direction(slope: float) -> str:
    if slope < -0.01:
        return 'improving'
    if slope > 0.01:
        return 'declining'
    return 'flat'


def _volatility_level(volatility: float) -> str:
    if volatility >= 0.8:
        return 'high'
    if volatility >= 0.3:
        return 'medium'
    return 'low'


def _phase_for_metrics(momentum_score: float, slope: float, volatility: float) -> tuple[str, str]:
    if momentum_score <= -0.2 or slope > 0.08:
        return 'recovery', 'negative momentum or steep decline slope'
    if volatility >= 0.8:
        return 'stabilization', 'volatility ceiling exceeded'
    if momentum_score <= 0.1:
        return 'stabilization', 'momentum below growth threshold'
    if momentum_score <= 0.3:
        return 'growth', 'momentum in growth band'
    if momentum_score <= 0.5:
        return 'acceleration', 'momentum in acceleration band'
    return 'dominance', 'sustained high momentum'


def integrate_temporal_state(
    db: Session,
    *,
    campaign_id: str,
    window: StrategyWindow,
    profile: StrategyEngineProfile,
    payload: dict,
) -> dict[str, object] | None:
    values, timestamps = _series(db, campaign_id=campaign_id, window=window, profile=profile)
    if len(values) < 3:
        return None

    slope = compute_slope(values, timestamps)
    acceleration = compute_acceleration(values, timestamps)
    trend_strength = compute_trend_strength(values)
    volatility = compute_volatility(values)

    # Lower avg_position is better, so invert slope for positive momentum semantics.
    momentum_score = _clamp((-slope) * trend_strength, -1.0, 1.0)
    volatility_penalty = _clamp(volatility * profile.volatility_penalty_weight, 0.0, 1.0)

    if payload.get('strategic_scores') is not None:
        base_score = float(payload['strategic_scores']['strategy_score']) / 100.0
        final_score = _clamp(base_score + (profile.momentum_weight * trend_strength * (1.0 if slope <= 0 else -1.0)) - volatility_penalty, 0.0, 1.0)
        payload['strategic_scores']['strategy_score'] = round(final_score * 100.0, 4)

    profile_hash = profile.version_hash()
    metric_name = 'rank_avg_position_momentum'
    deterministic_material = (
        f"{campaign_id}|{window.date_from.isoformat()}|{window.date_to.isoformat()}|{metric_name}|"
        f"{slope}|{acceleration}|{volatility}|{profile_hash}"
    )
    deterministic_hash = hashlib.sha256(deterministic_material.encode('utf-8')).hexdigest()

    metric_row = (
        db.query(MomentumMetric)
        .filter(
            MomentumMetric.campaign_id == campaign_id,
            MomentumMetric.metric_name == metric_name,
            MomentumMetric.computed_at == window.date_to,
        )
        .first()
    )
    if metric_row is None:
        metric_row = MomentumMetric(
            campaign_id=campaign_id,
            metric_name=metric_name,
            slope=slope,
            acceleration=acceleration,
            volatility=volatility,
            window_days=profile.trend_window_days,
            computed_at=window.date_to,
            deterministic_hash=deterministic_hash,
            profile_version=profile_hash,
        )
        db.add(metric_row)
    else:
        metric_row.slope = slope
        metric_row.acceleration = acceleration
        metric_row.volatility = volatility
        metric_row.window_days = profile.trend_window_days
        metric_row.deterministic_hash = deterministic_hash
        metric_row.profile_version = profile_hash

    new_phase, reason = _phase_for_metrics(momentum_score=momentum_score, slope=slope, volatility=volatility)
    latest_phase = (
        db.query(StrategyPhaseHistory)
        .filter(StrategyPhaseHistory.campaign_id == campaign_id)
        .order_by(StrategyPhaseHistory.effective_date.desc(), StrategyPhaseHistory.id.desc())
        .first()
    )

    if latest_phase is None or latest_phase.new_phase != new_phase:
        db.add(
            StrategyPhaseHistory(
                campaign_id=campaign_id,
                prior_phase=latest_phase.new_phase if latest_phase is not None else 'none',
                new_phase=new_phase,
                trigger_reason=reason,
                momentum_score=momentum_score,
                effective_date=window.date_to,
                version_hash=profile_hash,
            )
        )
    db.commit()

    visibility = {
        'current_strategy_phase': new_phase,
        'momentum_score': round(momentum_score, 6),
        'trend_direction': _trend_direction(slope),
        'volatility_level': _volatility_level(volatility),
        'profile_version_hash': profile_hash,
        'temporal_metric_computed_at': window.date_to.isoformat(),
    }
    payload.setdefault('meta', {})['temporal'] = visibility
    return visibility
