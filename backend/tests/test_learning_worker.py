from __future__ import annotations

from app.intelligence.workers.learning_worker import process


def test_learning_worker_executes_policy_learning_logic(monkeypatch) -> None:
    monkeypatch.setattr('app.intelligence.workers.learning_worker.update_policy_weights', lambda session: {'rec-a': 1.2})
    monkeypatch.setattr('app.intelligence.workers.learning_worker.update_policy_priority_weights', lambda session: {'policy-a': 0.8})
    monkeypatch.setattr('app.intelligence.workers.learning_worker.train_prediction_models', lambda session: {'trained': True, 'model_registry': {'rank_model_version': 'v2'}})
    monkeypatch.setattr('app.intelligence.workers.learning_worker.evolve_strategy_ecosystem', lambda session: {'experiments_created': 1})
    monkeypatch.setattr('app.intelligence.workers.learning_worker.run_global_intelligence_network', lambda session: {'causal_findings': 3})
    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr('app.intelligence.workers.learning_worker.publish_event', lambda event_type, payload: published.append((event_type, payload)))

    result = process({'campaign_id': 'campaign-1'})

    assert result['recommendation_weight_updates'] == {'rec-a': 1.2}
    assert result['policy_weight_updates'] == {'policy-a': 0.8}
    assert result['model_training']['trained'] is True
    assert result['strategy_evolution'] == {'experiments_created': 1}
    assert result['network_learning'] == {'causal_findings': 3}
    assert published and published[0][0] == 'policy.updated'
