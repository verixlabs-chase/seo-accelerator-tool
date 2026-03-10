from __future__ import annotations

from app.events import EventType
from app.intelligence.experiments.experiment_analysis import analyze_experiment
from app.intelligence.experiments.experiment_assignment import assign_campaign_to_experiment, deterministic_bucket
from app.intelligence.experiments.experiment_engine import apply_experiment_assignments
from app.intelligence.experiments.experiment_registry import ensure_experiment_for_policy
from app.intelligence.outcome_tracker import record_outcome
from app.intelligence.portfolio.portfolio_models import PolicyAllocation
from app.models.experiment import Experiment, ExperimentAssignment, ExperimentOutcome
from app.models.intelligence import StrategyRecommendation
from app.utils.enum_guard import ensure_enum
from app.enums import StrategyRecommendationStatus


def test_experiment_creation_and_deterministic_assignment(db_session, intelligence_graph) -> None:
    campaign = intelligence_graph['campaigns'][0]

    experiment = ensure_experiment_for_policy(db_session, policy_id='policy-a', industry='local')
    assignment = assign_campaign_to_experiment(db_session, campaign_id=campaign.id, experiment=experiment)

    assert db_session.query(Experiment).count() >= 1
    assert db_session.query(ExperimentAssignment).count() >= 1
    assert assignment.bucket == deterministic_bucket(campaign.id, experiment.experiment_id)
    assert assignment.cohort in {'control', 'treatment'}


def test_treatment_control_split_is_stable() -> None:
    buckets = [deterministic_bucket(f'campaign-{idx}', 'experiment-1') for idx in range(20)]
    control = sum(1 for bucket in buckets if bucket < 70)
    treatment = sum(1 for bucket in buckets if bucket >= 70)

    assert control > 0
    assert treatment > 0


def test_portfolio_allocation_applies_experiment_assignments(db_session, intelligence_graph) -> None:
    campaign = intelligence_graph['campaigns'][0]

    allocations = [
        PolicyAllocation(policy_id='baseline-policy', campaign_id=campaign.id, industry='local', mode='exploit', success_score=0.8, confidence=0.7),
        PolicyAllocation(policy_id='experimental-policy', campaign_id=campaign.id, industry='local', mode='explore', success_score=0.4, confidence=0.2),
    ]
    final_allocations, assignments = apply_experiment_assignments(db_session, campaign_id=campaign.id, industry='local', allocations=allocations)

    assert any(item.policy_id == 'baseline-policy' for item in final_allocations)
    assert assignments
    assert assignments[0]['policy_id'] == 'experimental-policy'


def test_outcome_attribution_and_effect_size(db_session, intelligence_graph, monkeypatch) -> None:
    control_campaign = intelligence_graph['campaigns'][0]
    treatment_campaign = intelligence_graph['campaigns'][1]

    control_rec = StrategyRecommendation(
        tenant_id=intelligence_graph['tenant'].id,
        campaign_id=control_campaign.id,
        recommendation_type='policy::policy-a::baseline',
        rationale='control',
        confidence=0.5,
        confidence_score=0.5,
        evidence_json='{"policy_id":"policy-a","industry":"local"}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.GENERATED, StrategyRecommendationStatus),
    )
    treatment_rec = StrategyRecommendation(
        tenant_id=intelligence_graph['tenant'].id,
        campaign_id=treatment_campaign.id,
        recommendation_type='policy::policy-a::treatment',
        rationale='treatment',
        confidence=0.5,
        confidence_score=0.5,
        evidence_json='{"policy_id":"policy-a","industry":"local"}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.GENERATED, StrategyRecommendationStatus),
    )
    db_session.add_all([control_rec, treatment_rec])
    db_session.flush()

    experiment = ensure_experiment_for_policy(db_session, policy_id='policy-a', industry='local', cohort_size=2)
    control_assignment = assign_campaign_to_experiment(db_session, campaign_id=control_campaign.id, experiment=experiment)
    treatment_assignment = assign_campaign_to_experiment(db_session, campaign_id=treatment_campaign.id, experiment=experiment)

    control_assignment.cohort = 'control'
    control_assignment.assigned_policy_id = 'baseline::policy-a'
    treatment_assignment.cohort = 'treatment'
    treatment_assignment.assigned_policy_id = 'policy-a'
    db_session.commit()

    published: list[tuple[str, dict]] = []
    monkeypatch.setattr('app.intelligence.outcome_tracker.publish_event', lambda event_type, payload: published.append((event_type, payload)))

    control_outcome = record_outcome(db_session, recommendation_id=control_rec.id, campaign_id=control_campaign.id, metric_before=100.0, metric_after=95.0, emit_learning_event=False)
    treatment_outcome = record_outcome(db_session, recommendation_id=treatment_rec.id, campaign_id=treatment_campaign.id, metric_before=100.0, metric_after=120.0, emit_learning_event=False)

    assert db_session.query(ExperimentOutcome).filter(ExperimentOutcome.outcome_id == control_outcome.id).count() == 1
    assert db_session.query(ExperimentOutcome).filter(ExperimentOutcome.outcome_id == treatment_outcome.id).count() == 1

    result = analyze_experiment(db_session, experiment_id=experiment.experiment_id)
    assert result is not None
    assert result.treatment_success_rate == 1.0
    assert result.control_success_rate == 0.0
    assert result.effect_size == 1.0
    assert result.confidence == 1.0
    assert any(event_type == EventType.EXPERIMENT_COMPLETED.value for event_type, _payload in published)
