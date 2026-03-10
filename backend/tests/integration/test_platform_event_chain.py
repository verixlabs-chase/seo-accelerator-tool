from __future__ import annotations

from app.intelligence.outcome_tracker import record_outcome
from app.intelligence.workers.causal_worker import process as process_causal_worker
from app.intelligence.workers.evolution_worker import process as process_evolution_worker
from app.models.experiment import Experiment, ExperimentOutcome
from app.models.knowledge_graph import KnowledgeEdge
from app.models.learning_metric_snapshot import LearningMetricSnapshot
from app.models.policy_performance import PolicyPerformance


def test_outcome_tracking_updates_portfolio_and_experiment_tables(db_session, intelligence_graph) -> None:
    recommendation = intelligence_graph['recommendations'][1]
    campaign = intelligence_graph['campaigns'][1]

    before = (
        db_session.query(PolicyPerformance)
        .filter(
            PolicyPerformance.policy_id == 'child-a',
            PolicyPerformance.campaign_id == campaign.id,
        )
        .one()
    )
    outcome = record_outcome(
        db_session,
        recommendation_id=recommendation.id,
        campaign_id=campaign.id,
        metric_before=100.0,
        metric_after=115.0,
        emit_learning_event=False,
    )

    db_session.expire_all()

    updated_rows = (
        db_session.query(PolicyPerformance)
        .filter(
            PolicyPerformance.policy_id == 'child-a',
            PolicyPerformance.campaign_id == campaign.id,
        )
        .all()
    )
    experiment_outcome = (
        db_session.query(ExperimentOutcome)
        .filter(ExperimentOutcome.outcome_id == outcome.id)
        .one()
    )

    assert updated_rows
    assert max(float(row.success_score) for row in updated_rows) >= float(before.success_score)
    assert experiment_outcome.campaign_id == campaign.id
    assert experiment_outcome.delta == outcome.delta


def test_experiment_event_pipeline_updates_graph_and_triggers_evolution(db_session, intelligence_graph) -> None:
    initial_experiment_count = db_session.query(Experiment).count()

    causal = process_causal_worker(
        db_session,
        {
            'policy_id': 'parent-a',
            'effect_size': 0.85,
            'confidence': 0.95,
            'industry': 'local',
            'sample_size': 24,
            'source_node': 'internal_link_ratio',
            'target_node': 'outcome::success',
        },
    )
    evolution = process_evolution_worker(
        db_session,
        {
            'industry': 'local',
            'confidence': 0.95,
            'effect_threshold': 0.2,
        },
    )
    db_session.commit()

    db_session.expire_all()

    edge = (
        db_session.query(KnowledgeEdge)
        .filter(KnowledgeEdge.edge_type == 'policy_outcome', KnowledgeEdge.industry == 'local')
        .first()
    )
    evolved = (
        db_session.query(Experiment)
        .filter(Experiment.policy_id == 'parent-a_experimental', Experiment.industry == 'local')
        .first()
    )

    assert causal['policy_id'] == 'parent-a'
    assert edge is not None
    assert float(edge.effect_size) > 0
    assert evolved is not None
    assert db_session.query(Experiment).count() >= initial_experiment_count + 1
    assert db_session.query(LearningMetricSnapshot).count() >= 1
    assert evolution['industry'] == 'local'
