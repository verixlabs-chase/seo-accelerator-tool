from __future__ import annotations

from datetime import UTC, datetime

from app.intelligence.telemetry.learning_metrics_engine import snapshot_learning_metrics_payload
from app.models.causal_edge import CausalEdge
from app.models.experiment import ExperimentOutcome
from app.models.learning_metric_snapshot import LearningMetricSnapshot
from app.models.policy_performance import PolicyPerformance
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.strategy_evolution_log import StrategyEvolutionLog


def test_learning_metrics_snapshot_computes_expected_values(db_session, intelligence_graph) -> None:
    graph = intelligence_graph
    db_session.add_all(
        [
            CausalEdge(source_node='industry::local', target_node='outcome::success', policy_id='child-a', effect_size=0.4, confidence=0.8, sample_size=10, industry='local'),
            CausalEdge(source_node='industry::local', target_node='outcome::success', policy_id='child-b', effect_size=0.2, confidence=0.6, sample_size=8, industry='local'),
        ]
    )
    db_session.flush()

    out_control_1 = RecommendationOutcome(recommendation_id='r1', campaign_id='camp-1', metric_before=100.0, metric_after=90.0, delta=-10.0, measured_at=datetime.now(UTC))
    out_treat_1 = RecommendationOutcome(recommendation_id='r2', campaign_id='camp-2', metric_before=100.0, metric_after=120.0, delta=20.0, measured_at=datetime.now(UTC))
    out_control_2 = RecommendationOutcome(recommendation_id='r3', campaign_id='camp-3', metric_before=100.0, metric_after=110.0, delta=10.0, measured_at=datetime.now(UTC))
    out_treat_2 = RecommendationOutcome(recommendation_id='r4', campaign_id='camp-4', metric_before=100.0, metric_after=95.0, delta=-5.0, measured_at=datetime.now(UTC))
    db_session.add_all([out_control_1, out_treat_1, out_control_2, out_treat_2])
    db_session.flush()

    assignments = list(graph['assignments'])
    experiments = list(graph['experiments'])
    db_session.add_all(
        [
            ExperimentOutcome(experiment_id=experiments[0].experiment_id, assignment_id=assignments[0].id, outcome_id=out_control_1.id, campaign_id='camp-1', metric_before=100.0, metric_after=90.0, delta=-10.0, success_flag=0.0),
            ExperimentOutcome(experiment_id=experiments[0].experiment_id, assignment_id=assignments[1].id, outcome_id=out_treat_1.id, campaign_id='camp-2', metric_before=100.0, metric_after=120.0, delta=20.0, success_flag=1.0),
            ExperimentOutcome(experiment_id=experiments[1].experiment_id, assignment_id=assignments[2].id, outcome_id=out_control_2.id, campaign_id='camp-3', metric_before=100.0, metric_after=110.0, delta=10.0, success_flag=1.0),
            ExperimentOutcome(experiment_id=experiments[1].experiment_id, assignment_id=assignments[3].id, outcome_id=out_treat_2.id, campaign_id='camp-4', metric_before=100.0, metric_after=95.0, delta=-5.0, success_flag=0.0),
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
