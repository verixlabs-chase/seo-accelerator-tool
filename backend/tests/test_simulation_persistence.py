from app.intelligence.digital_twin.strategy_simulation_engine import simulate_strategy
from app.intelligence.digital_twin.twin_state_model import DigitalTwinState
from app.models.digital_twin_simulation import DigitalTwinSimulation
from tests.conftest import create_test_campaign


def test_simulation_persists_prediction_record(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Persist Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Persist Org')
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Persist Campaign', domain='persist.example')

    twin_state = DigitalTwinState(
        campaign_id=campaign.id,
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

    result = simulate_strategy(twin_state, actions, db=db_session, strategy_id='primary')
    db_session.commit()

    assert result['simulation_id'] is not None

    row = db_session.get(DigitalTwinSimulation, str(result['simulation_id']))
    assert row is not None
    assert row.campaign_id == campaign.id
    assert row.strategy_actions == actions
    assert row.predicted_rank_delta == result['predicted_rank_delta']
    assert row.predicted_traffic_delta == result['predicted_traffic_delta']
    assert row.confidence == result['confidence']
    assert row.expected_value == result['expected_value']
    assert row.selected_strategy is False
