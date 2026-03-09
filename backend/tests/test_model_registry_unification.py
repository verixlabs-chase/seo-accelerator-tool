from app.intelligence.digital_twin.models.model_registry import get_model_parameters as get_twin_registry
from app.intelligence.model_registry import load_model_parameters, register_model, update_model_parameters
from app.intelligence.predictive_models.prediction_registry import get_model_parameters as get_predictive_registry


def test_unified_model_registry_updates_shared_state() -> None:
    register_model('forecast_model', 'v2', {'bias': 0.2, 'momentum_weight': 0.9})
    update_model_parameters('confidence_estimator', {'base': 0.55, 'minimum': 0.1}, version='v3')

    predictive = get_predictive_registry()
    twin = get_twin_registry()
    confidence = load_model_parameters('confidence_estimator')

    assert predictive['rank_model']['bias'] == 0.2
    assert twin['confidence_model_version'] == 'v3'
    assert confidence['minimum'] == 0.1
