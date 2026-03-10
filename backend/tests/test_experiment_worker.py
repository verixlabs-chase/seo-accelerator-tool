from __future__ import annotations

from sqlalchemy.orm import aliased

from app.intelligence.causal.causal_learning_engine import learn_from_experiment_completed
from app.intelligence.workers.causal_worker import process as process_causal_worker
from app.intelligence.workers.evolution_worker import process as process_evolution_worker
from app.intelligence.workers.experiment_worker import process as process_experiment_worker
from app.models.knowledge_graph import KnowledgeEdge, KnowledgeNode
from app.models.learning_metric_snapshot import LearningMetricSnapshot
from app.models.learning_report import LearningReport


def test_experiment_worker_triggers_causal_and_evolution_workers(monkeypatch, intelligence_graph) -> None:
    recommendation = intelligence_graph['recommendations'][0]
    order: list[str] = []
    monkeypatch.setattr('app.intelligence.workers.experiment_worker.process_causal_worker', lambda session, payload: order.append('causal') or {'policy_id': payload['policy_id']})
    monkeypatch.setattr('app.intelligence.workers.experiment_worker.process_evolution_worker', lambda session, payload: order.append('evolution') or {'registered_policies': [{'policy_id': f"{payload['policy_id']}_experimental"}]})

    result = process_experiment_worker({'policy_id': recommendation.recommendation_type.removeprefix('policy::'), 'industry': 'local'})

    assert order == ['causal', 'evolution']
    assert result['causal']['policy_id'] == recommendation.recommendation_type.removeprefix('policy::')
    assert result['evolution']['registered_policies'][0]['policy_id'] == f"{recommendation.recommendation_type.removeprefix('policy::')}_experimental"



def test_causal_worker_updates_causal_graph(db_session, intelligence_graph) -> None:
    recommendation = intelligence_graph['recommendations'][0]
    policy_id = recommendation.recommendation_type.removeprefix('policy::')
    result = process_causal_worker(
        db_session,
        {
            'policy_id': policy_id,
            'effect_size': 0.4,
            'confidence': 0.9,
            'industry': 'local',
            'sample_size': 10,
            'source_node': 'industry::local',
            'target_node': 'outcome::success',
        },
    )
    db_session.commit()

    policy = aliased(KnowledgeNode)
    assert result['policy_id'] == policy_id
    assert (
        db_session.query(KnowledgeEdge)
        .join(policy, KnowledgeEdge.source_node_id == policy.id)
        .filter(KnowledgeEdge.edge_type == 'policy_outcome', policy.node_key == policy_id)
        .count()
        == 1
    )



def test_evolution_worker_generates_metrics_and_reports(db_session, intelligence_graph) -> None:
    policy_id = intelligence_graph['policy_performance'][0].policy_id
    learn_from_experiment_completed(
        db_session,
        {
            'policy_id': policy_id,
            'effect_size': 0.4,
            'confidence': 0.88,
            'sample_size': 9,
            'industry': 'local',
            'source_node': 'industry::local',
            'target_node': 'outcome::success',
        },
    )
    db_session.commit()

    result = process_evolution_worker(db_session, {'policy_id': policy_id, 'industry': 'local', 'confidence': 0.88})
    db_session.commit()

    assert result['registered_policies'][0]['policy_id'] == f'{policy_id}_experimental'
    assert db_session.query(LearningMetricSnapshot).count() == 1
    assert db_session.query(LearningReport).count() == 1
