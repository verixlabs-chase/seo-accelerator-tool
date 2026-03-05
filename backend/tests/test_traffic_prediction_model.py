from app.intelligence.digital_twin.models.model_registry import reset_model_registry
from app.intelligence.digital_twin.models.traffic_prediction_model import TrafficPredictionModel


def test_traffic_prediction_model_uses_rank_and_baseline() -> None:
    reset_model_registry()
    model = TrafficPredictionModel()

    result = model.predict_traffic_delta(rank_delta=2.5, baseline_traffic=100.0)

    assert result == 17.5
