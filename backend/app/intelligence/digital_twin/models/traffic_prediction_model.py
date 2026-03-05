from __future__ import annotations

from app.intelligence.digital_twin.models.model_registry import get_model_parameters


class TrafficPredictionModel:
    def __init__(self, traffic_factor: float | None = None) -> None:
        if traffic_factor is not None:
            self.traffic_factor = float(traffic_factor)
            return
        self.traffic_factor = float(get_model_parameters().get('traffic_factor', 0.07))

    def predict_traffic_delta(self, rank_delta: float, baseline_traffic: float) -> float:
        safe_rank_delta = float(rank_delta)
        safe_baseline_traffic = max(0.0, float(baseline_traffic))
        traffic_delta = safe_baseline_traffic * (safe_rank_delta * self.traffic_factor)
        return round(traffic_delta, 6)
