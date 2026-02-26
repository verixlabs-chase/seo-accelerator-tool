from __future__ import annotations

from app.services.strategy_engine.temporal_math import PRECISION

DEFAULT_IMPACT_WEIGHT = 1.0
STAGNATION_BAND = 0.01
VOLATILITY_THRESHOLD = 0.75


def compute_relative_momentum_score(our_slope: float, competitor_slope: float, impact_weight: float = DEFAULT_IMPACT_WEIGHT) -> float:
    return round((float(our_slope) - float(competitor_slope)) * float(impact_weight), PRECISION)


def classify_relative_momentum(
    our_slope: float,
    competitor_slope: float,
    volatility: float,
    impact_weight: float = DEFAULT_IMPACT_WEIGHT,
) -> str:
    score = compute_relative_momentum_score(our_slope=our_slope, competitor_slope=competitor_slope, impact_weight=impact_weight)
    if float(volatility) >= VOLATILITY_THRESHOLD:
        return 'volatile'
    if abs(score) <= STAGNATION_BAND:
        return 'stagnating'
    if score > 0:
        return 'gaining_ground'
    return 'losing_ground'
