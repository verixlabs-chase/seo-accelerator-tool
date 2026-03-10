from __future__ import annotations

from app.events import EventType, publish_event
from app.events.queue import dispatch_worker_job
from app.events.subscriber_registry import register_default_subscribers
from app.models.causal_edge import CausalEdge
from app.models.experiment import Experiment
from app.models.learning_metric_snapshot import LearningMetricSnapshot
from app.models.learning_report import LearningReport
from app.models.strategy_evolution_log import StrategyEvolutionLog


def test_experiment_event_is_processed_by_background_worker_chain(db_session) -> None:
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

    assert db_session.query(CausalEdge).filter(CausalEdge.policy_id == 'increase_internal_links').count() == 1
    assert db_session.query(StrategyEvolutionLog).filter(StrategyEvolutionLog.new_policy == 'increase_internal_links_more').count() == 1
    assert db_session.query(Experiment).filter(Experiment.policy_id == 'increase_internal_links_more').count() == 1
    assert db_session.query(LearningMetricSnapshot).count() == 1
    assert db_session.query(LearningReport).count() == 1


def test_queue_dispatch_returns_inline_result_in_tests(db_session) -> None:
    result = dispatch_worker_job(
        'experiment',
        {
            'policy_id': 'add_location_pages',
            'effect_size': 0.4,
            'confidence': 0.88,
            'industry': 'local',
            'sample_size': 9,
            'source_node': 'industry::local',
            'target_node': 'outcome::success',
        },
    )

    assert result['worker'] == 'experiment'
    assert result['mode'] == 'inline'
    assert result['result']['causal']['policy_id'] == 'add_location_pages'
    assert result['result']['evolution']['registered_policies'][0]['policy_id'] == 'add_location_pages_cluster'
