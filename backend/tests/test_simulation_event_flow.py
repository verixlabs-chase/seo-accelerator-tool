from app.enums import StrategyRecommendationStatus
from app.events import EventType, publish_event, subscribe
from app.events.subscriber_registry import register_default_subscribers, reset_registry
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


def test_simulation_event_flow_schedules_execution(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Simulation Flow Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Simulation Flow Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Simulation Flow Campaign',
        domain='simulation-flow.example',
    )

    recommendation = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='content_improvement',
        rationale='test event pipeline execution schedule',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='{}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
        idempotency_key='simulation-event-flow',
    )
    db_session.add(recommendation)
    db_session.commit()

    reset_registry()
    register_default_subscribers()

    seen: dict[str, int] = {'simulation_completed': 0, 'execution_scheduled': 0}
    subscribe(
        EventType.SIMULATION_COMPLETED.value,
        lambda _payload: seen.__setitem__('simulation_completed', seen['simulation_completed'] + 1),
    )
    subscribe(
        EventType.EXECUTION_SCHEDULED.value,
        lambda _payload: seen.__setitem__('execution_scheduled', seen['execution_scheduled'] + 1),
    )

    publish_event(
        EventType.RECOMMENDATION_GENERATED.value,
        {
            'campaign_id': campaign.id,
            'candidate_strategies': [
                {
                    'strategy_id': 'candidate_low',
                    'recommendation_id': recommendation.id,
                    'strategy_actions': [{'type': 'publish_content', 'pages': 1}],
                },
                {
                    'strategy_id': 'candidate_high',
                    'recommendation_id': recommendation.id,
                    'strategy_actions': [
                        {'type': 'publish_content', 'pages': 2},
                        {'type': 'fix_technical_issues', 'count': 2},
                    ],
                },
            ],
        },
    )

    executions = (
        db_session.query(RecommendationExecution)
        .filter(RecommendationExecution.recommendation_id == recommendation.id)
        .all()
    )

    assert seen['simulation_completed'] >= 1
    assert seen['execution_scheduled'] >= 1
    assert len(executions) == 1

    reset_registry()
