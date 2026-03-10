from app.intelligence.digital_twin.strategy_optimizer import optimize_strategy
from app.intelligence.digital_twin.twin_state_model import DigitalTwinState


def test_optimize_strategy_selects_highest_expected_value(db_session) -> None:
    twin_state = DigitalTwinState(
        campaign_id='c1',
        avg_rank=12.0,
        traffic_estimate=80.0,
        technical_issue_count=12,
        internal_link_count=5,
        content_page_count=4,
        review_velocity=0.0,
        local_health_score=0.5,
        momentum_score=-0.2,
    )

    candidates = [
        {
            'strategy_id': 'links_only',
            'strategy_actions': [{'type': 'internal_link', 'count': 2}],
        },
        {
            'strategy_id': 'content_plus_fixes',
            'strategy_actions': [
                {'type': 'publish_content', 'pages': 2},
                {'type': 'fix_technical_issues', 'count': 2},
            ],
        },
    ]

    best = optimize_strategy(twin_state, candidates)

    assert best is not None
    assert best['strategy_id'] == 'content_plus_fixes'
    assert best['expected_value'] > 0
