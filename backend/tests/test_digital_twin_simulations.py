from app.intelligence.digital_twin.strategy_optimizer import optimize_strategy
from app.intelligence.digital_twin.twin_state_model import DigitalTwinState
from app.models.digital_twin_simulation import DigitalTwinSimulation
from tests.conftest import create_test_campaign


def test_optimizer_marks_selected_strategy_on_simulation_rows(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Twin Sim Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Twin Sim Org')
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Twin Sim Campaign', domain='twinsim.example')

    twin_state = DigitalTwinState(
        campaign_id=campaign.id,
        avg_rank=10.0,
        traffic_estimate=100.0,
        technical_issue_count=6,
        internal_link_count=8,
        content_page_count=5,
        review_velocity=0.0,
        local_health_score=0.7,
        momentum_score=0.2,
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
                {'type': 'fix_technical_issues', 'count': 1},
            ],
        },
    ]

    best = optimize_strategy(twin_state, candidates, db=db_session)
    db_session.commit()

    assert best is not None
    rows = (
        db_session.query(DigitalTwinSimulation)
        .filter(DigitalTwinSimulation.campaign_id == campaign.id)
        .order_by(DigitalTwinSimulation.created_at.asc(), DigitalTwinSimulation.id.asc())
        .all()
    )
    assert len(rows) == 2

    selected_rows = [row for row in rows if row.selected_strategy]
    assert len(selected_rows) == 1
    assert selected_rows[0].id == best['simulation']['simulation_id']
    assert selected_rows[0].expected_value == best['expected_value']
