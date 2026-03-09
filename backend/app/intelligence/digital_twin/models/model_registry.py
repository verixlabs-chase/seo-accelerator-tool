from __future__ import annotations

from typing import Any

from app.intelligence.model_registry import (
    initialize_default_models,
    load_model_parameters,
    register_model,
    snapshot_registry,
    update_model_parameters as update_registry_model_parameters,
)


def get_model_parameters() -> dict[str, Any]:
    initialize_default_models()
    rank = load_model_parameters('rank_prediction_model')
    traffic = load_model_parameters('traffic_prediction_model')
    confidence = load_model_parameters('confidence_estimator')
    registry = snapshot_registry()
    return {
        'rank_model_version': str(registry.get('rank_prediction_model', {}).get('version', 'v1')),
        'coefficients': rank,
        'traffic_model_version': str(registry.get('traffic_prediction_model', {}).get('version', 'v1')),
        'traffic_factor': float(traffic.get('traffic_factor', 0.07)),
        'confidence_model_version': str(registry.get('confidence_estimator', {}).get('version', 'v1')),
        'confidence_parameters': confidence,
    }


def replace_model_parameters(values: dict[str, Any]) -> dict[str, Any]:
    rank_version = str(values.get('rank_model_version', 'v1') or 'v1')
    traffic_version = str(values.get('traffic_model_version', 'v1') or 'v1')
    confidence_version = str(values.get('confidence_model_version', 'v1') or 'v1')
    register_model('rank_prediction_model', rank_version, dict(values.get('coefficients', {})))
    register_model('traffic_prediction_model', traffic_version, {'traffic_factor': float(values.get('traffic_factor', 0.07))})
    register_model('confidence_estimator', confidence_version, dict(values.get('confidence_parameters', {})))
    return get_model_parameters()


def update_model_parameters(updates: dict[str, Any]) -> dict[str, Any]:
    registry = get_model_parameters()
    if 'coefficients' in updates and isinstance(updates['coefficients'], dict):
        update_registry_model_parameters(
            'rank_prediction_model',
            dict(updates['coefficients']),
            version=str(updates.get('rank_model_version', registry['rank_model_version'])),
        )
    if 'traffic_factor' in updates:
        update_registry_model_parameters(
            'traffic_prediction_model',
            {'traffic_factor': float(updates['traffic_factor'])},
            version=str(updates.get('traffic_model_version', registry['traffic_model_version'])),
        )
    if 'confidence_parameters' in updates and isinstance(updates['confidence_parameters'], dict):
        update_registry_model_parameters(
            'confidence_estimator',
            dict(updates['confidence_parameters']),
            version=str(updates.get('confidence_model_version', registry['confidence_model_version'])),
        )
    return get_model_parameters()


def reset_model_registry() -> dict[str, Any]:
    initialize_default_models()
    return get_model_parameters()
