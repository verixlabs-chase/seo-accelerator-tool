from datetime import UTC, datetime

from app.enums import StrategyRecommendationStatus
from app.intelligence.strategy_evolution.strategy_experiment_engine import create_strategy_experiments
from app.intelligence.strategy_evolution.strategy_lifecycle_manager import evolve_strategy_ecosystem
from app.intelligence.strategy_evolution.strategy_performance_analyzer import analyze_strategy_performance
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.strategy_experiment import StrategyExperiment
from app.models.strategy_performance import StrategyPerformance
from tests.conftest import create_test_campaign


def test_strategy_performance_analysis_and_lifecycle(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(tenant_id='tenant-1', name='Evolution Tenant')
    org = create_test_org(organization_id=tenant.id, tenant_id=tenant.id, name='Evolution Org')
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Evolution Campaign', domain='evolution.example')

    for idx, delta in enumerate([3.0, 2.5, 2.0], start=1):
        recommendation = StrategyRecommendation(
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            recommendation_type='policy::prioritize_internal_linking::add_contextual_links',
            rationale='test',
            confidence=0.8,
            confidence_score=0.8,
            evidence_json='[]',
            risk_tier=1,
            rollback_plan_json='{}',
            status=StrategyRecommendationStatus.EXECUTED,
            idempotency_key=f'evolution-{idx}',
        )
        db_session.add(recommendation)
        db_session.flush()
        db_session.add(
            RecommendationOutcome(
                recommendation_id=recommendation.id,
                campaign_id=campaign.id,
                metric_before=10.0,
                metric_after=10.0 + delta,
                delta=delta,
                measured_at=datetime.now(UTC),
            )
        )
    db_session.commit()

    summaries = analyze_strategy_performance(db_session)
    assert summaries
    assert summaries[0]['strategy_id'] == 'policy::prioritize_internal_linking::add_contextual_links'

    result = evolve_strategy_ecosystem(db_session)
    db_session.commit()

    performance = db_session.get(StrategyPerformance, 'policy::prioritize_internal_linking::add_contextual_links')
    assert performance is not None
    assert performance.lifecycle_stage == 'promoted'
    assert result['strategies_analyzed'] >= 1


def test_strategy_experiment_engine_creates_variants(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Experiment Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Experiment Org')
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Experiment Campaign', domain='experiment.example')
    performance = StrategyPerformance(
        strategy_id='policy::prioritize_internal_linking::add_contextual_links',
        recommendation_type='policy::prioritize_internal_linking::add_contextual_links',
        lifecycle_stage='promoted',
        performance_score=0.82,
        win_rate=0.9,
        avg_delta=1.1,
        sample_size=4,
        graph_score=0.2,
        industry_prior=0.1,
        metadata_json={'campaign_id': campaign.id},
    )
    db_session.add(performance)
    db_session.commit()

    class StubTwinState:
        campaign_id = campaign.id
        avg_rank = 10.0
        traffic_estimate = 100.0
        technical_issue_count = 2
        internal_link_count = 10
        content_page_count = 5
        review_velocity = 0.0
        local_health_score = 0.0
        momentum_score = 0.1

    def build_stub(_db, _campaign_id):
        return StubTwinState()

    def simulate_stub(_twin_state, strategy_actions, **_kwargs):
        return {
            'predicted_rank_delta': float(strategy_actions[0].get('count', strategy_actions[0].get('pages', 1))),
            'predicted_traffic_delta': 2.0,
            'confidence': 0.7,
            'expected_value': 0.9,
        }

    experiments = create_strategy_experiments(
        db_session,
        twin_state_builder=build_stub,
        simulate_fn=simulate_stub,
    )
    db_session.commit()

    assert experiments
    assert db_session.query(StrategyExperiment).count() >= 1
