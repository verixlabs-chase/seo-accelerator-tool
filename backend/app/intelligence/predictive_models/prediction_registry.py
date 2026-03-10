from __future__ import annotations

from typing import Any

from app.intelligence.model_registry import (
    initialize_default_models,
    load_model_parameters,
    snapshot_registry,
    update_model_parameters as update_registry_model_parameters,
)


def get_model_parameters() -> dict[str, Any]:
    initialize_default_models()
    forecast_parameters = load_model_parameters('forecast_model')
    confidence_parameters = load_model_parameters('confidence_estimator')
    return {
        'rank_model': {
            'bias': float(forecast_parameters.get('bias', 0.05)),
            'momentum_weight': float(forecast_parameters.get('momentum_weight', 0.6)),
            'support_weight': float(forecast_parameters.get('support_weight', 0.15)),
            'industry_success_weight': float(forecast_parameters.get('industry_success_weight', 1.1)),
            'graph_confidence_weight': float(forecast_parameters.get('graph_confidence_weight', 0.9)),
            'outcome_delta_weight': float(forecast_parameters.get('outcome_delta_weight', 0.8)),
        },
        'traffic_model': {
            'traffic_factor': float(forecast_parameters.get('traffic_factor', 0.08)),
        },
        'confidence_model': {
            'sample_factor': float(confidence_parameters.get('sample_size_norm', 120.0)),
            'variance_penalty': float(confidence_parameters.get('variance_weight', 0.75)),
            'minimum': float(confidence_parameters.get('minimum', 0.05)),
        },
        'risk_model': {
            'volatility_weight': float(forecast_parameters.get('volatility_weight', 0.7)),
            'confidence_weight': float(forecast_parameters.get('confidence_weight', 0.6)),
        },
    }


def update_model_parameters(updates: dict[str, Any]) -> dict[str, Any]:
    current = snapshot_registry()
    forecast = dict(current.get('forecast_model', {}).get('parameters', {}))
    confidence = dict(current.get('confidence_estimator', {}).get('parameters', {}))
    for key, value in updates.items():
        if key in {'rank_model', 'traffic_model', 'risk_model'} and isinstance(value, dict):
            forecast.update(value)
        elif key == 'confidence_model' and isinstance(value, dict):
            if 'sample_factor' in value:
                confidence['sample_size_norm'] = value['sample_factor']
            if 'variance_penalty' in value:
                confidence['variance_weight'] = value['variance_penalty']
            if 'minimum' in value:
                confidence['minimum'] = value['minimum']
    update_registry_model_parameters('forecast_model', forecast)
    update_registry_model_parameters('confidence_estimator', confidence)
    return get_model_parameters()


def reset_model() -> dict[str, Any]:
    initialize_default_models()
    return get_model_parameters()
