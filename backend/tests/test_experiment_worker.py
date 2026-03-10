from __future__ import annotations

from app.intelligence.workers.experiment_worker import process as process_experiment_worker
from app.intelligence.workers.causal_worker import process as process_causal_worker
from app.intelligence.workers.evolution_worker import process as process_evolution_worker
from app.models.causal_edge import CausalEdge
from app.models.learning_metric_snapshot import LearningMetricSnapshot
from app.models.learning_report import LearningReport


def test_experiment_worker_triggers_causal_and_evolution_workers(monkeypatch) -> None:
    order: list[str] = []
    monkeypatch.setattr('app.intelligence.workers.experiment_worker.process_causal_worker', lambda session, payload: order.append('causal') or {'policy_id': 'p1'})
    monkeypatch.setattr('app.intelligence.workers.experiment_worker.process_evolution_worker', lambda session, payload: order.append('evolution') or {'registered_policies': [{'policy_id': 'child-p1'}]})

    result = process_experiment_worker({'policy_id': 'p1', 'industry': 'local'})

    assert order == ['causal', 'evolution']
    assert result['causal']['policy_id'] == 'p1'
    assert result['evolution']['registered_policies'][0]['policy_id'] == 'child-p1'


def test_causal_worker_updates_causal_graph(db_session) -> None:
    result = process_causal_worker(
        db_session,
        {
            'policy_id': 'increase_internal_links',
            'effect_size': 0.4,
            'confidence': 0.9,
            'industry': 'local',
            'sample_size': 10,
            'source_node': 'industry::local',
            'target_node': 'outcome::success',
        },
    )
    db_session.commit()

    assert result['policy_id'] == 'increase_internal_links'
    assert db_session.query(CausalEdge).filter(CausalEdge.policy_id == 'increase_internal_links').count() == 1


def test_evolution_worker_generates_metrics_and_reports(db_session) -> None:
    db_session.add(
        CausalEdge(
            source_node='industry::local',
            target_node='outcome::success',
            policy_id='add_location_pages',
            effect_size=0.4,
            confidence=0.88,
            sample_size=9,
            industry='local',
        )
    )
    db_session.commit()

    result = process_evolution_worker(db_session, {'policy_id': 'add_location_pages', 'industry': 'local', 'confidence': 0.88})
    db_session.commit()

    assert result['registered_policies'][0]['policy_id'] == 'add_location_pages_cluster'
    assert db_session.query(LearningMetricSnapshot).count() == 1
    assert db_session.query(LearningReport).count() == 1
