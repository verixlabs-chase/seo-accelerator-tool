from __future__ import annotations

import math

from app.intelligence.predictive_models.prediction_registry import get_model_parameters


def predict_rank_delta(features: dict[str, float]) -> float:
    params = get_model_parameters().get('rank_model', {})

    bias = float(params.get('bias', 0.0))
    momentum_weight = float(params.get('momentum_weight', 0.5))
    support_weight = float(params.get('support_weight', 0.1))
    industry_weight = float(params.get('industry_success_weight', 1.0))
    graph_weight = float(params.get('graph_confidence_weight', 0.8))
    outcome_weight = float(params.get('outcome_delta_weight', 0.7))

    momentum = float(features.get('campaign_momentum_score', 0.0))
    support = float(features.get('graph_support', 0.0))
    industry_success = float(features.get('industry_success_rate', 0.0))
    graph_confidence = float(features.get('graph_confidence_avg', 0.0))
    outcome_delta = float(features.get('historical_outcome_delta', 0.0))

    linear = (
        bias
        + (momentum * momentum_weight)
        + (math.log1p(max(support, 0.0)) * support_weight)
        + (industry_success * industry_weight)
        + (graph_confidence * graph_weight)
        + (outcome_delta * outcome_weight)
    )
    return round(linear, 6)


def predict_traffic_delta(rank_delta: float, baseline_traffic: float) -> float:
    params = get_model_parameters().get('traffic_model', {})
    traffic_factor = float(params.get('traffic_factor', 0.08))

    safe_baseline = max(float(baseline_traffic), 0.0)
    delta = safe_baseline * (float(rank_delta) * traffic_factor)
    return round(delta, 6)


def predict_confidence(sample_size: float, outcome_variance: float) -> float:
    params = get_model_parameters().get('confidence_model', {})
    sample_factor = float(params.get('sample_factor', 120.0))
    variance_penalty = float(params.get('variance_penalty', 0.75))
    minimum = float(params.get('minimum', 0.05))

    support_component = min(1.0, max(0.0, float(sample_size) / max(sample_factor, 1.0)))
    variance_component = max(0.0, 1.0 - (float(outcome_variance) * variance_penalty))
    confidence = support_component * variance_component
    return round(max(minimum, min(1.0, confidence)), 6)


def predict_risk_score(confidence: float, volatility: float) -> float:
    params = get_model_parameters().get('risk_model', {})
    volatility_weight = float(params.get('volatility_weight', 0.7))
    confidence_weight = float(params.get('confidence_weight', 0.6))

    base_risk = (float(volatility) * volatility_weight) + ((1.0 - float(confidence)) * confidence_weight)
    return round(max(0.0, min(1.0, base_risk)), 6)
