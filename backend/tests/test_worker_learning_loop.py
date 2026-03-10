from __future__ import annotations

from sqlalchemy.orm import aliased

from app.events import EventType, publish_event
from app.events.queue import reset_queue_state
from app.events.subscriber_registry import register_default_subscribers
from app.intelligence.intelligence_orchestrator import run_campaign_cycle
from app.models.experiment import Experiment
from app.models.knowledge_graph import KnowledgeEdge, KnowledgeNode
from app.models.learning_metric_snapshot import LearningMetricSnapshot
from app.models.strategy_evolution_log import StrategyEvolutionLog
from tests.conftest import create_test_campaign


def test_experiment_completed_runs_async_learning_loop(db_session) -> None:
    reset_queue_state()
    register_default_subscribers(force_reset=True)

    publish_event(
        EventType.EXPERIMENT_COMPLETED.value,
        {
            'policy_id': 'increase_internal_links',
            'effect_size': 0.45,
            'confidence': 0.9,
            'industry': 'local',
            'sample_size': 10,
            'source_node': 'industry::local',
            'target_node': 'outcome::success',
        },
    )

    policy = aliased(KnowledgeNode)
    assert (
        db_session.query(KnowledgeEdge)
        .join(policy, KnowledgeEdge.source_node_id == policy.id)
        .filter(KnowledgeEdge.edge_type == 'policy_outcome', policy.node_key == 'increase_internal_links')
        .count()
        == 1
    )
    assert db_session.query(StrategyEvolutionLog).filter(StrategyEvolutionLog.new_policy == 'increase_internal_links_more').count() == 1
    assert db_session.query(Experiment).filter(Experiment.policy_id == 'increase_internal_links_more').count() == 1
    assert db_session.query(LearningMetricSnapshot).count() == 1



def test_campaign_cycle_completes_without_running_learning_workers_inline(db_session, create_test_tenant, create_test_org, monkeypatch) -> None:
    tenant = create_test_tenant(name='Worker Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Worker Org')
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Worker Campaign', domain='worker.example')
    campaign.setup_state = 'Active'
    db_session.commit()

    queued: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr('app.events.queue.dispatch_worker_job', lambda worker_name, payload: queued.append((worker_name, dict(payload))) or {'worker': worker_name, 'status': 'queued'})

    summary = run_campaign_cycle(campaign.id, db=db_session)

    assert summary['campaign_id'] == campaign.id
    assert summary['executions_completed'] >= 0
    assert summary['policy_learning']['recommendation_weight_count'] == 0
    assert any(worker == 'experiment' for worker, _payload in queued) or any(worker == 'learning' for worker, _payload in queued)
