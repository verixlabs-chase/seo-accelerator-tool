from app.intelligence.digital_twin.models.model_registry import reset_model_registry
from app.intelligence.digital_twin.models.rank_prediction_model import RankPredictionModel


def test_rank_prediction_model_returns_deterministic_delta(db_session) -> None:
    reset_model_registry()
    model = RankPredictionModel()
    features = {
        'technical_issue_count': 10,
        'avg_rank': 9.0,
        'momentum_score': 0.2,
        'cohort_pattern_strength': 0.5,
    }
    actions = [
        {'type': 'internal_link', 'count': 5},
        {'type': 'publish_content', 'pages': 2},
        {'type': 'fix_technical_issues', 'count': 3},
    ]

    first = model.predict_rank_delta(features, actions)
    second = model.predict_rank_delta(features, actions)

    assert first == second
    assert first == 2.584
