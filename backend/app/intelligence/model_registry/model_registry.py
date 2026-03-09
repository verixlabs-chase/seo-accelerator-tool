from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.intelligence.model_registry_store import get_registry_payload, update_registry_payload

_REGISTRY_NAME = 'autonomous_model_registry'

_DEFAULT_MODELS: dict[str, dict[str, Any]] = {
    'rank_prediction_model': {
        'version': 'v1',
        'parameters': {
            'internal_links_added': 0.18,
            'pages_added': 0.42,
            'issues_fixed': 0.26,
            'momentum_score': 0.12,
            'cohort_pattern_strength': 0.08,
            'avg_rank_bias': 0.0,
            'technical_issue_penalty': 0.0,
        },
    },
    'traffic_prediction_model': {
        'version': 'v1',
        'parameters': {
            'traffic_factor': 0.07,
        },
    },
    'confidence_estimator': {
        'version': 'v1',
        'parameters': {
            'base': 0.45,
            'pattern_weight': 0.25,
            'sample_weight': 0.30,
            'cohort_weight': 0.10,
            'variance_weight': 0.10,
            'sample_size_norm': 20.0,
            'historical_variance_baseline': 0.25,
            'minimum': 0.05,
        },
    },
    'forecast_model': {
        'version': 'v1',
        'parameters': {
            'bias': 0.05,
            'momentum_weight': 0.6,
            'support_weight': 0.15,
            'industry_success_weight': 1.1,
            'graph_confidence_weight': 0.9,
            'outcome_delta_weight': 0.8,
            'traffic_factor': 0.08,
            'volatility_weight': 0.7,
            'confidence_weight': 0.6,
        },
    },
}


def initialize_default_models() -> dict[str, dict[str, Any]]:
    return get_registry_payload(_REGISTRY_NAME, _DEFAULT_MODELS)


def snapshot_registry() -> dict[str, dict[str, Any]]:
    return get_registry_payload(_REGISTRY_NAME, _DEFAULT_MODELS)


def register_model(model_name: str, version: str, parameters: dict[str, Any]) -> dict[str, Any]:
    updates = {model_name: {'version': str(version), 'parameters': deepcopy(parameters)}}
    payload = update_registry_payload(_REGISTRY_NAME, updates, _DEFAULT_MODELS)
    return deepcopy(payload[model_name])


def load_model_parameters(model_name: str) -> dict[str, Any]:
    payload = snapshot_registry()
    model = payload.get(model_name, {})
    parameters = model.get('parameters', {}) if isinstance(model, dict) else {}
    return deepcopy(parameters if isinstance(parameters, dict) else {})


def update_model_parameters(model_name: str, parameters: dict[str, Any], version: str | None = None) -> dict[str, Any]:
    payload = snapshot_registry()
    current = payload.get(model_name, {})
    current_version = str(current.get('version', 'v1') or 'v1') if isinstance(current, dict) else 'v1'
    updates = {
        model_name: {
            'version': str(version or current_version),
            'parameters': deepcopy(parameters),
        }
    }
    merged = update_registry_payload(_REGISTRY_NAME, updates, _DEFAULT_MODELS)
    model = merged.get(model_name, {})
    return deepcopy(model if isinstance(model, dict) else {})
