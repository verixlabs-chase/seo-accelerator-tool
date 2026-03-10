from __future__ import annotations

from app.events import EventType, publish_event
from app.events.subscriber_registry import register_default_subscribers
from app.intelligence.evolution.strategy_evolution_engine import evolve_strategies
from app.models.causal_edge import CausalEdge
from app.models.experiment import Experiment
from app.models.intelligence_model_registry import IntelligenceModelRegistryState
from app.models.policy_weights import PolicyWeight
from app.models.strategy_evolution_log import StrategyEvolutionLog


def test_causal_insights_generate_mutations_and_trigger_experiments(db_session, intelligence_graph) -> None:
    _ = intelligence_graph
    db_session.add_all(
        [
            CausalEdge(source_node='industry::local', target_node='outcome::success', policy_id='increase_internal_links', effect_size=0.42, confidence=0.91, sample_size=18, industry='local'),
            CausalEdge(source_node='industry::local', target_node='outcome::success', policy_id='add_location_pages', effect_size=0.33, confidence=0.82, sample_size=15, industry='local'),
            CausalEdge(source_node='industry::local', target_node='outcome::success', policy_id='weak_policy', effect_size=0.05, confidence=0.4, sample_size=9, industry='local'),
        ]
    )
    db_session.commit()

    result = evolve_strategies(db_session, industry='local', effect_threshold=0.2, confidence_threshold=0.7)
    db_session.commit()

    assert [item.policy_id for item in result.candidates] == ['increase_internal_links', 'add_location_pages']
    assert [item.new_policy for item in result.mutations] == ['increase_internal_links_more', 'add_location_pages_cluster']
    assert {item.status for item in result.registered_policies} == {'experimental'}
    assert len(result.experiments_triggered) == 2

    registry = db_session.get(IntelligenceModelRegistryState, 'policy_registry')
    assert registry is not None
    policies = dict(registry.payload.get('policies') or {})
    assert policies['increase_internal_links_more']['status'] == 'experimental'
    assert policies['add_location_pages_cluster']['parent_policy'] == 'add_location_pages'

    assert db_session.query(StrategyEvolutionLog).count() == 4
    assert db_session.query(Experiment).filter(Experiment.experiment_type == 'strategy_evolution').count() >= 2
    assert db_session.get(PolicyWeight, 'policy::increase_internal_links_more') is not None
    assert db_session.get(PolicyWeight, 'policy::add_location_pages_cluster') is not None


def test_evolution_engine_is_idempotent_for_existing_mutations(db_session, intelligence_graph) -> None:
    _ = intelligence_graph
    db_session.add(
        CausalEdge(
            source_node='industry::local',
            target_node='outcome::success',
            policy_id='increase_internal_links',
            effect_size=0.5,
            confidence=0.9,
            sample_size=20,
            industry='local',
        )
    )
    db_session.commit()

    first = evolve_strategies(db_session, industry='local')
    db_session.commit()
    second = evolve_strategies(db_session, industry='local')
    db_session.commit()

    assert len(first.experiments_triggered) >= 1
    assert len(second.experiments_triggered) >= 1
    assert db_session.query(StrategyEvolutionLog).filter(StrategyEvolutionLog.new_policy == 'increase_internal_links_more').count() == 1
    assert db_session.query(Experiment).filter(Experiment.policy_id == 'increase_internal_links_more').count() == 1


def test_evolution_processor_runs_after_causal_learning_on_experiment_completed(db_session) -> None:
    register_default_subscribers(force_reset=True)

    publish_event(
        EventType.EXPERIMENT_COMPLETED.value,
        {
            'policy_id': 'increase_internal_links',
            'effect_size': 0.44,
            'confidence': 0.92,
            'industry': 'local',
            'sample_size': 12,
            'source_node': 'industry::local',
            'target_node': 'outcome::success',
        },
    )

    assert db_session.query(CausalEdge).filter(CausalEdge.policy_id == 'increase_internal_links').count() == 1
    assert db_session.query(StrategyEvolutionLog).filter(StrategyEvolutionLog.new_policy == 'increase_internal_links_more').count() == 1
    assert db_session.query(Experiment).filter(Experiment.policy_id == 'increase_internal_links_more').count() == 1


def test_evolution_caps_limit_new_experiments_per_cycle(db_session, intelligence_graph) -> None:
    _ = intelligence_graph
    db_session.add_all(
        [
            CausalEdge(source_node='industry::local', target_node='outcome::success', policy_id='increase_internal_links', effect_size=0.4, confidence=0.9, sample_size=10, industry='local'),
            CausalEdge(source_node='industry::local', target_node='outcome::success', policy_id='add_location_pages', effect_size=0.35, confidence=0.88, sample_size=11, industry='local'),
        ]
    )
    db_session.commit()

    result = evolve_strategies(db_session, industry='local', max_new_experiments_per_cycle=1)
    db_session.commit()

    assert len(result.mutations) == 2
    assert len(result.experiments_triggered) == 1
    assert db_session.query(Experiment).filter(Experiment.experiment_type == 'strategy_evolution').count() >= 1
