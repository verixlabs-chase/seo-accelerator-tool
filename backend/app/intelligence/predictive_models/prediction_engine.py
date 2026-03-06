from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.predictive_models.prediction_feature_builder import build_prediction_features
from app.intelligence.predictive_models.strategy_forecast_model import (
    predict_confidence,
    predict_rank_delta,
    predict_risk_score,
    predict_traffic_delta,
)


def predict_strategy_outcome(campaign_id: str, strategy: dict[str, Any], db: Session | None = None) -> dict[str, float]:
    features = build_prediction_features(campaign_id, strategy, db=db)

    predicted_rank_delta = predict_rank_delta(features)
    predicted_traffic_delta = predict_traffic_delta(predicted_rank_delta, float(features.get('baseline_traffic', 0.0)))
    confidence_score = predict_confidence(
        float(features.get('sample_size', 1.0)),
        float(features.get('outcome_variance', 0.0)),
    )
    risk_score = predict_risk_score(confidence_score, float(features.get('outcome_variance', 0.0)))

    return {
        'predicted_rank_delta': round(float(predicted_rank_delta), 6),
        'predicted_traffic_delta': round(float(predicted_traffic_delta), 6),
        'confidence_score': round(float(confidence_score), 6),
        'risk_score': round(float(risk_score), 6),
    }
