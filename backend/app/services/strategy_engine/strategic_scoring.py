from __future__ import annotations

from app.services.strategy_engine.scenario_registry import SCENARIO_INDEX
from app.services.strategy_engine.schemas import CampaignStrategyOut, StrategicScoreOut

MIN_SCORE = 0.0
MAX_SCORE = 100.0
NORMALIZED_MAX = 1.0
NEUTRAL_NORMALIZED = 0.5

_IMPACT_SEVERITY: dict[str, float] = {
    "low": 1.0 / 3.0,
    "medium": 2.0 / 3.0,
    "high": 1.0,
}


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


def _to_100(value: float) -> float:
    return round(_clamp(value * MAX_SCORE, MIN_SCORE, MAX_SCORE), 4)


def _weighted_average(values: list[float], weights: list[float], neutral: float = NEUTRAL_NORMALIZED) -> float:
    if not values or not weights:
        return neutral
    total_weight = sum(weights)
    if total_weight <= 0:
        return neutral
    weighted_sum = sum(value * weight for value, weight in zip(values, weights, strict=False))
    return _clamp(weighted_sum / total_weight, MIN_SCORE, NORMALIZED_MAX)


def compute_strategic_scores(strategy_output: CampaignStrategyOut) -> StrategicScoreOut:
    tier = str(strategy_output.meta.get("tier", "")).strip().lower()
    is_enterprise = tier == "enterprise"
    if not strategy_output.recommendations:
        return StrategicScoreOut(
            strategy_score=_to_100(NEUTRAL_NORMALIZED),
            technical_health_score=_to_100(NEUTRAL_NORMALIZED),
            competitive_pressure_score=_to_100(NEUTRAL_NORMALIZED) if is_enterprise else None,
            local_authority_score=_to_100(NEUTRAL_NORMALIZED),
            risk_index=_to_100(NEUTRAL_NORMALIZED),
            opportunity_index=_to_100(NEUTRAL_NORMALIZED),
        )

    all_risk: list[float] = []
    all_opportunity: list[float] = []
    all_weights: list[float] = []
    technical_risk: list[float] = []
    technical_weights: list[float] = []
    local_pressure: list[float] = []
    local_weights: list[float] = []
    competitive_pressure: list[float] = []
    competitive_weights: list[float] = []

    for rec in strategy_output.recommendations:
        scenario = SCENARIO_INDEX.get(rec.scenario_id)
        if scenario is None:
            continue

        impact_weight = _clamp(scenario.impact_weight, MIN_SCORE, NORMALIZED_MAX)
        confidence = _clamp(rec.confidence, MIN_SCORE, NORMALIZED_MAX)
        priority = _clamp(rec.priority_score, MIN_SCORE, NORMALIZED_MAX)
        severity = _IMPACT_SEVERITY.get(rec.impact_level.lower(), _IMPACT_SEVERITY["medium"])

        weight = impact_weight * confidence
        risk_signal = _clamp(priority * severity, MIN_SCORE, NORMALIZED_MAX)
        opportunity_signal = _clamp(priority * confidence * (NORMALIZED_MAX - (severity / 2.0)), MIN_SCORE, NORMALIZED_MAX)

        all_weights.append(weight)
        all_risk.append(risk_signal)
        all_opportunity.append(opportunity_signal)

        if scenario.category == "technical":
            technical_risk.append(risk_signal)
            technical_weights.append(weight)
        if scenario.category in {"gbp", "local"}:
            local_pressure.append(risk_signal)
            local_weights.append(weight)
        if scenario.category == "competitive":
            competitive_pressure.append(risk_signal)
            competitive_weights.append(weight)

    risk_index_norm = _weighted_average(all_risk, all_weights)
    opportunity_norm = _weighted_average(all_opportunity, all_weights)
    technical_health_norm = NORMALIZED_MAX - _weighted_average(technical_risk, technical_weights)
    local_authority_norm = NORMALIZED_MAX - _weighted_average(local_pressure, local_weights)

    competitive_pressure_norm: float | None
    if is_enterprise:
        competitive_pressure_norm = _weighted_average(competitive_pressure, competitive_weights)
        competitive_health_norm = NORMALIZED_MAX - competitive_pressure_norm
    else:
        competitive_pressure_norm = None
        competitive_health_norm = NEUTRAL_NORMALIZED

    strategy_norm = _weighted_average(
        [
            technical_health_norm,
            local_authority_norm,
            competitive_health_norm,
            NORMALIZED_MAX - risk_index_norm,
            opportunity_norm,
        ],
        [NORMALIZED_MAX, NORMALIZED_MAX, NORMALIZED_MAX, NORMALIZED_MAX, NORMALIZED_MAX],
    )

    return StrategicScoreOut(
        strategy_score=_to_100(strategy_norm),
        technical_health_score=_to_100(technical_health_norm),
        competitive_pressure_score=_to_100(competitive_pressure_norm) if competitive_pressure_norm is not None else None,
        local_authority_score=_to_100(local_authority_norm),
        risk_index=_to_100(risk_index_norm),
        opportunity_index=_to_100(opportunity_norm),
    )

