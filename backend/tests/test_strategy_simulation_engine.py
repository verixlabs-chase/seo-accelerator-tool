from app.intelligence.digital_twin.models.model_registry import reset_model_registry
from app.intelligence.digital_twin.strategy_simulation_engine import simulate_strategy
from app.intelligence.digital_twin.twin_state_model import DigitalTwinState


def test_simulate_strategy_is_deterministic(db_session) -> None:
    reset_model_registry()

    twin_state = DigitalTwinState(
        campaign_id='c1',
        avg_rank=9.0,
        traffic_estimate=120.0,
        technical_issue_count=10,
        internal_link_count=20,
        content_page_count=12,
        review_velocity=2.0,
        local_health_score=0.8,
        momentum_score=0.1,
    )
    actions = [
        {'type': 'internal_link', 'count': 5},
        {'type': 'publish_content', 'pages': 2},
        {'type': 'fix_technical_issues', 'count': 3},
    ]

    first = simulate_strategy(twin_state, actions)
    second = simulate_strategy(twin_state, actions)

    assert first == second
    assert first['predicted_rank_delta'] == 2.532
    assert first['predicted_traffic_delta'] == 21.2688
    assert first['confidence'] == 0.68
