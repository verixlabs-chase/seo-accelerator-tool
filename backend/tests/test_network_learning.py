from datetime import UTC, datetime

from app.enums import StrategyRecommendationStatus
from app.intelligence.network_learning.causal_outcome_analyzer import analyze_causal_outcomes
from app.intelligence.network_learning.global_intelligence_network import run_global_intelligence_network
from app.intelligence.network_learning.industry_similarity_engine import compute_industry_similarity_matrix, similarity_allows_transfer
from app.intelligence.network_learning.seo_flight_recorder import record_seo_flight
from app.models.campaign import Campaign
from app.models.execution_mutation import ExecutionMutation
from app.models.industry_intelligence import IndustryIntelligenceModel
from app.models.recommendation_execution import RecommendationExecution
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.seo_mutation_outcome import SEOMutationOutcome
from app.models.strategy_experiment import StrategyExperiment
from app.models.intelligence import StrategyRecommendation


def test_seo_flight_recorder_persists_mutation_outcomes(db_session) -> None:
    campaign = Campaign(tenant_id='tenant-1', organization_id=None, portfolio_id=None, sub_account_id=None, name='Flight Campaign', domain='flight.example')
    db_session.add(campaign)
    db_session.flush()
    recommendation = StrategyRecommendation(
        tenant_id='tenant-1',
        campaign_id=campaign.id,
        recommendation_type='policy::prioritize_internal_linking::add_contextual_links',
        rationale='test',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='[]',
        risk_tier=1,
        rollback_plan_json='{}',
        status=StrategyRecommendationStatus.EXECUTED,
        idempotency_key='flight-rec-1',
    )
    db_session.add(recommendation)
    db_session.flush()
    execution = RecommendationExecution(
        recommendation_id=recommendation.id,
        campaign_id=campaign.id,
        execution_type='improve_internal_links',
        execution_payload='{}',
        idempotency_key='flight-exec-1',
        deterministic_hash='hash',
        status='completed',
    )
    db_session.add(execution)
    db_session.flush()
    db_session.add(ExecutionMutation(execution_id=execution.id, recommendation_id=recommendation.id, campaign_id=campaign.id, mutation_type='insert_internal_link', target_url='/service/a', mutation_payload='{}', status='applied'))
    db_session.add(RecommendationOutcome(recommendation_id=recommendation.id, campaign_id=campaign.id, metric_before=9.0, metric_after=7.5, delta=-1.5, measured_at=datetime.now(UTC)))
    db_session.commit()

    rows = record_seo_flight(db_session, execution_id=execution.id, industry_id='legal')
    db_session.commit()

    assert rows
    persisted = db_session.query(SEOMutationOutcome).all()
    assert len(persisted) == 1
    assert persisted[0].mutation_type == 'insert_internal_link'
    assert persisted[0].industry_id == 'legal'
    assert persisted[0].mutation_parameters == {}


def test_network_learning_respects_industry_similarity_thresholds(db_session) -> None:
    db_session.add(IndustryIntelligenceModel(industry_id='legal', industry_name='Legal', pattern_distribution={'internal_link_problem': 1.0}, strategy_success_rates={'insert_internal_link': 0.8}, avg_rank_delta=1.0, avg_traffic_delta=2.0, confidence_score=0.8, sample_size=10, support_state={}))
    db_session.add(IndustryIntelligenceModel(industry_id='ecommerce', industry_name='Ecommerce', pattern_distribution={'schema_gap': 1.0}, strategy_success_rates={'add_schema_markup': 0.7}, avg_rank_delta=0.5, avg_traffic_delta=1.0, confidence_score=0.7, sample_size=8, support_state={}))
    db_session.add(SEOMutationOutcome(execution_id='exec-1', mutation_id=None, campaign_id='camp-1', industry_id='legal', mutation_type='insert_internal_link', page_url='/a', rank_before=10.0, rank_after=7.0, traffic_before=100.0, traffic_after=120.0, measured_delta=-3.0))
    db_session.commit()

    similarity = compute_industry_similarity_matrix(db_session)
    assert similarity
    assert similarity_allows_transfer(db_session, 'legal', 'legal') is True
    assert similarity_allows_transfer(db_session, 'legal', 'ecommerce') is False

    findings = analyze_causal_outcomes(db_session, target_industry_id='ecommerce')
    assert findings == []


def test_global_network_syncs_experiment_results(db_session) -> None:
    experiment = StrategyExperiment(
        strategy_id='policy::prioritize_internal_linking::add_contextual_links',
        variant_strategy_id='policy::prioritize_internal_linking::add_contextual_links::variant_1',
        campaign_id=None,
        hypothesis='test',
        mutation_payload=[{'type': 'internal_link', 'count': 5}],
        predicted_rank_delta=1.0,
        predicted_traffic_delta=2.0,
        confidence=0.7,
        expected_value=0.8,
        status='proposed',
        metadata_json={'industry': 'unknown'},
    )
    db_session.add(experiment)
    db_session.commit()

    result = run_global_intelligence_network(db_session)
    db_session.commit()

    assert result['experiment_results_synced'] >= 1
