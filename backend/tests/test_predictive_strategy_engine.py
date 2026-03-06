from __future__ import annotations

from typing import Any

from app.intelligence.predictive_models.prediction_engine import predict_strategy_outcome
from app.intelligence.predictive_models.prediction_feature_builder import build_prediction_features
from app.intelligence.predictive_models.strategy_forecast_model import (
    predict_confidence,
    predict_rank_delta,
    predict_traffic_delta,
)


def test_prediction_features_generated_correctly(monkeypatch: Any) -> None:
    class _FakeIndustry:
        def get_strategy_success_rate(self, _industry_id: str, _strategy: str) -> float:
            return 0.77

    class _FakeGraph:
        def get_relevant_strategies(self, **_kwargs: Any) -> list[dict[str, Any]]:
            return [
                {
                    'strategy_id': 'strategy:repair_internal_links',
                    'evidence': [
                        {'confidence': 0.8},
                        {'confidence': 0.6},
                    ],
                }
            ]

    monkeypatch.setattr(
        'app.intelligence.predictive_models.prediction_feature_builder.get_industry_query_engine',
        lambda: _FakeIndustry(),
    )
    monkeypatch.setattr(
        'app.intelligence.predictive_models.prediction_feature_builder.get_graph_query_engine',
        lambda: _FakeGraph(),
    )

    features = build_prediction_features(
        campaign_id='campaign-a',
        strategy={'strategy_id': 'strategy:repair_internal_links', 'industry': 'roofing', 'baseline_traffic': 500.0},
        db=None,
    )

    assert features['industry_success_rate'] == 0.77
    assert features['graph_support'] == 2.0
    assert round(features['graph_confidence_avg'], 2) == 0.7
    assert features['baseline_traffic'] == 500.0


def test_rank_and_traffic_predictions_work() -> None:
    features = {
        'campaign_momentum_score': 0.3,
        'graph_support': 10.0,
        'industry_success_rate': 0.8,
        'graph_confidence_avg': 0.7,
        'historical_outcome_delta': 0.6,
    }
    rank_delta = predict_rank_delta(features)
    traffic_delta = predict_traffic_delta(rank_delta, baseline_traffic=1000.0)

    assert rank_delta > 0
    assert traffic_delta > 0


def test_confidence_score_bounded_correctly() -> None:
    low = predict_confidence(sample_size=1.0, outcome_variance=10.0)
    high = predict_confidence(sample_size=500.0, outcome_variance=0.01)

    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0
    assert high >= low


def test_prediction_engine_integrates_with_strategy(monkeypatch: Any) -> None:
    class _FakeIndustry:
        def get_strategy_success_rate(self, _industry_id: str, _strategy: str) -> float:
            return 0.65

    class _FakeGraph:
        def get_relevant_strategies(self, **_kwargs: Any) -> list[dict[str, Any]]:
            return [
                {
                    'strategy_id': 'strategy:publish_cluster_content',
                    'evidence': [{'confidence': 0.8}],
                }
            ]

    monkeypatch.setattr(
        'app.intelligence.predictive_models.prediction_feature_builder.get_industry_query_engine',
        lambda: _FakeIndustry(),
    )
    monkeypatch.setattr(
        'app.intelligence.predictive_models.prediction_feature_builder.get_graph_query_engine',
        lambda: _FakeGraph(),
    )

    outcome = predict_strategy_outcome(
        'campaign-b',
        {'strategy_id': 'strategy:publish_cluster_content', 'industry': 'saas', 'baseline_traffic': 800.0},
        db=None,
    )

    assert set(outcome.keys()) == {
        'predicted_rank_delta',
        'predicted_traffic_delta',
        'confidence_score',
        'risk_score',
    }
    assert isinstance(outcome['predicted_rank_delta'], float)
    assert isinstance(outcome['predicted_traffic_delta'], float)
    assert 0.0 <= outcome['confidence_score'] <= 1.0
    assert 0.0 <= outcome['risk_score'] <= 1.0
