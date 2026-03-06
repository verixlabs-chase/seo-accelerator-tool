from __future__ import annotations

from copy import deepcopy
from typing import Any

_DEFAULT_PARAMETERS: dict[str, Any] = {
    'rank_model': {
        'bias': 0.05,
        'momentum_weight': 0.6,
        'support_weight': 0.15,
        'industry_success_weight': 1.1,
        'graph_confidence_weight': 0.9,
        'outcome_delta_weight': 0.8,
    },
    'traffic_model': {
        'traffic_factor': 0.08,
    },
    'confidence_model': {
        'sample_factor': 120.0,
        'variance_penalty': 0.75,
        'minimum': 0.05,
    },
    'risk_model': {
        'volatility_weight': 0.7,
        'confidence_weight': 0.6,
    },
}

_MODEL_PARAMETERS: dict[str, Any] = deepcopy(_DEFAULT_PARAMETERS)


def get_model_parameters() -> dict[str, Any]:
    return deepcopy(_MODEL_PARAMETERS)


def update_model_parameters(updates: dict[str, Any]) -> dict[str, Any]:
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(_MODEL_PARAMETERS.get(key), dict):
            _MODEL_PARAMETERS[key].update(value)
        else:
            _MODEL_PARAMETERS[key] = value
    return get_model_parameters()


def reset_model() -> dict[str, Any]:
    _MODEL_PARAMETERS.clear()
    _MODEL_PARAMETERS.update(deepcopy(_DEFAULT_PARAMETERS))
    return get_model_parameters()
