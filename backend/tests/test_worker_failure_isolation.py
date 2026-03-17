from __future__ import annotations

from app.events import EventType, publish_event
from app.events.queue import list_failed_jobs, queue_stats, reset_queue_state, retry_failed_job
from app.events.subscriber_registry import register_default_subscribers
from app.intelligence.intelligence_orchestrator import run_campaign_cycle
from tests.conftest import create_test_campaign


def test_worker_failure_isolation_and_retry(monkeypatch) -> None:
    reset_queue_state()
    register_default_subscribers(force_reset=True)

    monkeypatch.setattr('app.intelligence.workers.run_worker', lambda worker_name, payload: (_ for _ in ()).throw(RuntimeError('boom')))
    publish_event(EventType.EXPERIMENT_COMPLETED.value, {'policy_id': 'p1', 'industry': 'local'})

    failures = list_failed_jobs()
    assert len(failures) == 1
    assert failures[0]['worker'] == 'experiment'

    monkeypatch.setattr('app.intelligence.workers.run_worker', lambda worker_name, payload: {'ok': True, 'worker': worker_name})
    retried = retry_failed_job(failures[0]['job_id'])
    assert retried['status'] == 'succeeded'
    assert list_failed_jobs() == []


def test_duplicate_events_are_idempotent(db_session) -> None:
    reset_queue_state()
    register_default_subscribers(force_reset=True)

    payload = {
        'policy_id': 'increase_internal_links',
        'effect_size': 0.45,
        'confidence': 0.9,
        'industry': 'local',
        'sample_size': 10,
        'source_node': 'industry::local',
        'target_node': 'outcome::success',
    }
    publish_event(EventType.EXPERIMENT_COMPLETED.value, payload)
    publish_event(EventType.EXPERIMENT_COMPLETED.value, payload)
    publish_event(EventType.OUTCOME_RECORDED.value, {'campaign_id': 'c1'})
    publish_event(EventType.OUTCOME_RECORDED.value, {'campaign_id': 'c1'})

    from app.models.experiment import Experiment
    from app.models.learning_metric_snapshot import LearningMetricSnapshot

    assert db_session.query(Experiment).filter(Experiment.policy_id == 'increase_internal_links_more').count() == 1
    assert db_session.query(LearningMetricSnapshot).count() == 1


def test_campaign_cycle_succeeds_even_if_worker_dispatch_fails(db_session, create_test_tenant, create_test_org, monkeypatch) -> None:
    tenant = create_test_tenant(name='Failure Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Failure Org')
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Failure Campaign', domain='failure.example')
    campaign.setup_state = 'Active'
    db_session.commit()

    monkeypatch.setattr('app.events.queue.dispatch_worker_job', lambda worker_name, payload: {'worker': worker_name, 'status': 'failed', 'error': 'queue-down'})
    monkeypatch.setattr('app.events.emitter._process_learning_event', lambda *args, **kwargs: None)

    summary = run_campaign_cycle(campaign.id, db=db_session)
    assert summary['campaign_id'] == campaign.id


def test_queue_stats_disclose_process_local_truth_scope() -> None:
    reset_queue_state()

    stats = queue_stats()

    assert stats['queue_depth'] == {}
    assert stats['worker_inflight_jobs'] == {}
    assert stats['truth_scope'] == {
        'mode': 'process_local',
        'durable': False,
        'multi_instance_safe': False,
        'warning': 'Queue depth and inflight counts reflect only the current process and are not cluster-wide operational truth.',
    }
