from __future__ import annotations

from datetime import UTC, datetime

from app.intelligence.telemetry.learning_metrics_engine import snapshot_learning_metrics_payload
from app.models.causal_edge import CausalEdge
from app.models.experiment import Experiment, ExperimentAssignment, ExperimentOutcome
from app.models.learning_metric_snapshot import LearningMetricSnapshot
from app.models.policy_performance import PolicyPerformance
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.strategy_evolution_log import StrategyEvolutionLog


def test_learning_metrics_snapshot_computes_expected_values(db_session) -> None:
    db_session.add_all(
        [
            StrategyEvolutionLog(parent_policy='parent-a', new_policy='child-a', mutation_type='extend_policy_variant'),
            StrategyEvolutionLog(parent_policy='parent-b', new_policy='child-b', mutation_type='extend_policy_variant'),
            PolicyPerformance(policy_id='parent-a', campaign_id='camp-1', industry='local', success_score=0.2, execution_count=3, confidence=0.3),
            PolicyPerformance(policy_id='child-a', campaign_id='camp-2', industry='local', success_score=0.5, execution_count=3, confidence=0.3),
            PolicyPerformance(policy_id='parent-b', campaign_id='camp-3', industry='local', success_score=0.6, execution_count=3, confidence=0.3),
            PolicyPerformance(policy_id='child-b', campaign_id='camp-4', industry='local', success_score=0.3, execution_count=3, confidence=0.3),
            CausalEdge(source_node='industry::local', target_node='outcome::success', policy_id='child-a', effect_size=0.4, confidence=0.8, sample_size=10, industry='local'),
            CausalEdge(source_node='industry::local', target_node='outcome::success', policy_id='child-b', effect_size=0.2, confidence=0.6, sample_size=8, industry='local'),
        ]
    )
    db_session.flush()

    exp_win = Experiment(policy_id='child-a', hypothesis='positive', experiment_type='strategy_evolution', cohort_size=10, status='completed', industry='local')
    exp_loss = Experiment(policy_id='child-b', hypothesis='negative', experiment_type='strategy_evolution', cohort_size=10, status='completed', industry='local')
    db_session.add_all([exp_win, exp_loss])
    db_session.flush()

    out_control_1 = RecommendationOutcome(recommendation_id='r1', campaign_id='camp-1', metric_before=100.0, metric_after=90.0, delta=-10.0, measured_at=datetime.now(UTC))
    out_treat_1 = RecommendationOutcome(recommendation_id='r2', campaign_id='camp-2', metric_before=100.0, metric_after=120.0, delta=20.0, measured_at=datetime.now(UTC))
    out_control_2 = RecommendationOutcome(recommendation_id='r3', campaign_id='camp-3', metric_before=100.0, metric_after=110.0, delta=10.0, measured_at=datetime.now(UTC))
    out_treat_2 = RecommendationOutcome(recommendation_id='r4', campaign_id='camp-4', metric_before=100.0, metric_after=95.0, delta=-5.0, measured_at=datetime.now(UTC))
    db_session.add_all([out_control_1, out_treat_1, out_control_2, out_treat_2])
    db_session.flush()

    assign_control_1 = ExperimentAssignment(experiment_id=exp_win.experiment_id, campaign_id='camp-1', cohort='control', bucket=10, assigned_policy_id='baseline::child-a')
    assign_treat_1 = ExperimentAssignment(experiment_id=exp_win.experiment_id, campaign_id='camp-2', cohort='treatment', bucket=80, assigned_policy_id='child-a')
    assign_control_2 = ExperimentAssignment(experiment_id=exp_loss.experiment_id, campaign_id='camp-3', cohort='control', bucket=10, assigned_policy_id='baseline::child-b')
    assign_treat_2 = ExperimentAssignment(experiment_id=exp_loss.experiment_id, campaign_id='camp-4', cohort='treatment', bucket=80, assigned_policy_id='child-b')
    db_session.add_all([assign_control_1, assign_treat_1, assign_control_2, assign_treat_2])
    db_session.flush()

    db_session.add_all(
        [
            ExperimentOutcome(experiment_id=exp_win.experiment_id, assignment_id=assign_control_1.id, outcome_id=out_control_1.id, campaign_id='camp-1', metric_before=100.0, metric_after=90.0, delta=-10.0, success_flag=0.0),
            ExperimentOutcome(experiment_id=exp_win.experiment_id, assignment_id=assign_treat_1.id, outcome_id=out_treat_1.id, campaign_id='camp-2', metric_before=100.0, metric_after=120.0, delta=20.0, success_flag=1.0),
            ExperimentOutcome(experiment_id=exp_loss.experiment_id, assignment_id=assign_control_2.id, outcome_id=out_control_2.id, campaign_id='camp-3', metric_before=100.0, metric_after=110.0, delta=10.0, success_flag=1.0),
            ExperimentOutcome(experiment_id=exp_loss.experiment_id, assignment_id=assign_treat_2.id, outcome_id=out_treat_2.id, campaign_id='camp-4', metric_before=100.0, metric_after=95.0, delta=-5.0, success_flag=0.0),
        ]
    )
    db_session.commit()

    payload = snapshot_learning_metrics_payload(db_session)
    db_session.commit()

    assert payload['mutation_count'] == 2
    assert payload['experiment_count'] == 2
    assert payload['mutation_success_rate'] == 0.5
    assert payload['experiment_win_rate'] == 0.5
    assert payload['causal_confidence_mean'] == 0.7
    assert payload['policy_improvement_velocity'] == 0.0
    assert db_session.query(LearningMetricSnapshot).count() == 1


def test_learning_metrics_snapshot_handles_empty_state(db_session) -> None:
    payload = snapshot_learning_metrics_payload(db_session)
    db_session.commit()

    assert payload['mutation_success_rate'] == 0.0
    assert payload['experiment_win_rate'] == 0.0
    assert payload['causal_confidence_mean'] == 0.0
    assert payload['policy_improvement_velocity'] == 0.0
    assert payload['mutation_count'] == 0
    assert payload['experiment_count'] == 0
