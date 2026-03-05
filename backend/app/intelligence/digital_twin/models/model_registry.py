from __future__ import annotations

from copy import deepcopy
from typing import Any

_DEFAULT_MODEL_PARAMETERS: dict[str, Any] = {
    'rank_model_version': 'v1',
    'coefficients': {
        'internal_links_added': 0.18,
        'pages_added': 0.42,
        'issues_fixed': 0.26,
        'momentum_score': 0.12,
        'cohort_pattern_strength': 0.08,
        'avg_rank_bias': 0.0,
        'technical_issue_penalty': 0.0,
    },
    'traffic_model_version': 'v1',
    'traffic_factor': 0.07,
    'confidence_model_version': 'v1',
    'confidence_parameters': {
        'base': 0.45,
        'pattern_weight': 0.25,
        'sample_weight': 0.30,
        'cohort_weight': 0.10,
        'variance_weight': 0.10,
        'sample_size_norm': 20.0,
        'historical_variance_baseline': 0.25,
    },
}

_MODEL_PARAMETERS: dict[str, Any] = deepcopy(_DEFAULT_MODEL_PARAMETERS)


def get_model_parameters() -> dict[str, Any]:
    return deepcopy(_MODEL_PARAMETERS)


def replace_model_parameters(values: dict[str, Any]) -> dict[str, Any]:
    global _MODEL_PARAMETERS
    _MODEL_PARAMETERS = deepcopy(values)
    return get_model_parameters()


def update_model_parameters(updates: dict[str, Any]) -> dict[str, Any]:
    _merge_in_place(_MODEL_PARAMETERS, updates)
    return get_model_parameters()


def reset_model_registry() -> dict[str, Any]:
    global _MODEL_PARAMETERS
    _MODEL_PARAMETERS = deepcopy(_DEFAULT_MODEL_PARAMETERS)
    return get_model_parameters()


def _merge_in_place(target: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_in_place(target[key], value)
            continue
        target[key] = value
