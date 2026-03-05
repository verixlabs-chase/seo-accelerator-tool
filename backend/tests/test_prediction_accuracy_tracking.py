from datetime import UTC, datetime

from app.enums import StrategyRecommendationStatus
from app.intelligence.intelligence_metrics_aggregator import compute_campaign_metrics
from app.intelligence.outcome_tracker import record_execution_outcome
from app.models.digital_twin_simulation import DigitalTwinSimulation
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.models.recommendation_outcome import RecommendationOutcome
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


def test_prediction_accuracy_tracking_links_outcome_and_computes_metrics(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Accuracy Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Accuracy Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Accuracy Campaign',
        domain='accuracy.example',
    )

    recommendation = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='create_content_brief',
        rationale='accuracy tracking test',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='{}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(recommendation)
    db_session.flush()

    simulation = DigitalTwinSimulation(
        campaign_id=campaign.id,
        strategy_actions=[{'type': 'publish_content', 'pages': 1}],
        predicted_rank_delta=2.0,
        predicted_traffic_delta=4.0,
        confidence=0.7,
        expected_value=1.4,
        selected_strategy=True,
        model_version='rank=v1;traffic=v1;confidence=v1',
        created_at=datetime.now(UTC),
    )
    db_session.add(simulation)
    db_session.flush()

    execution = RecommendationExecution(
        recommendation_id=recommendation.id,
        campaign_id=campaign.id,
        execution_type='create_content_brief',
        execution_payload='{}',
        idempotency_key=f'{recommendation.id}:create_content_brief:test',
        deterministic_hash='accuracy-hash',
        status='completed',
        created_at=datetime.now(UTC),
    )
    db_session.add(execution)
    db_session.flush()

    outcome = record_execution_outcome(
        db_session,
        execution=execution,
        metric_before=10.0,
        metric_after=13.0,
    )

    assert outcome.simulation_id == simulation.id

    linked = db_session.get(RecommendationOutcome, outcome.id)
    assert linked is not None
    assert linked.simulation_id == simulation.id

    snapshot = compute_campaign_metrics(campaign.id, db=db_session)
    assert snapshot.avg_prediction_error_rank == 1.0
    assert snapshot.avg_prediction_error_traffic == 1.0
    assert snapshot.prediction_accuracy_score == 0.75
