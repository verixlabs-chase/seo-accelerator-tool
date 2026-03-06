from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from app.events.event_types import EventType
from app.intelligence.event_processors import execution_processor, outcome_processor, pattern_processor, simulation_processor
from app.intelligence.global_graph.graph_service import get_graph_update_pipeline
from app.intelligence.strategy_transfer_engine import transfer_strategies


class _FakeSession:
    def commit(self) -> None:
        return None

    def close(self) -> None:
        return None


def test_strategy_transfer_uses_shared_graph_service() -> None:
    campaign_id = 'campaign-runtime-graph'
    updater = get_graph_update_pipeline()

    updater.update_from_pattern(
        {
            'campaign_id': campaign_id,
            'industry': 'home_services',
            'features': {'internal_link_ratio': 0.4},
            'patterns': [
                {
                    'pattern_key': 'internal_link_problem',
                    'confidence': 0.8,
                    'evidence': ['internal_link_ratio'],
                    'strategy_key': 'repair_internal_links',
                }
            ],
        }
    )
    updater.update_from_outcome(
        {
            'campaign_id': campaign_id,
            'strategy_id': 'repair_internal_links',
            'outcome_key': 'rank_position_change',
            'delta': 2.0,
            'confidence': 0.9,
            'is_causal': True,
            'industry': 'home_services',
        }
    )

    payload = transfer_strategies(
        campaign_id,
        industry='home_services',
        twin_state_builder=lambda _db, _campaign_id: object(),
        simulate_fn=lambda _twin_state, _actions, **kwargs: {
            'strategy_id': kwargs.get('strategy_id'),
            'confidence': 0.95,
            'expected_value': 1.7,
        },
    )

    assert payload['strategies']
    assert payload['strategies'][0]['strategy_id'] == 'strategy:repair_internal_links'


def test_simulation_and_pattern_processors_feed_graph(monkeypatch: Any) -> None:
    updates: list[tuple[str, dict[str, Any]]] = []

    class _FakeUpdater:
        def update_from_pattern(self, payload: dict[str, Any]) -> list[str]:
            updates.append(('pattern', payload))
            return ['p1']

        def update_from_simulation(self, payload: dict[str, Any]) -> list[str]:
            updates.append(('simulation', payload))
            return ['s1']

    monkeypatch.setattr(pattern_processor, 'get_graph_update_pipeline', lambda: _FakeUpdater())
    monkeypatch.setattr(simulation_processor, 'get_graph_update_pipeline', lambda: _FakeUpdater())
    monkeypatch.setattr(pattern_processor, 'discover_patterns_for_campaign', lambda *_args, **_kwargs: [{'pattern_key': 'x', 'confidence': 0.7, 'evidence': ['f1']}])
    monkeypatch.setattr(pattern_processor, 'discover_cohort_patterns', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(pattern_processor, 'SessionLocal', lambda: _FakeSession())
    monkeypatch.setattr(simulation_processor, 'SessionLocal', lambda: _FakeSession())
    monkeypatch.setattr(simulation_processor.DigitalTwinState, 'from_campaign_data', lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        simulation_processor,
        'optimize_strategy',
        lambda *_args, **_kwargs: {
            'strategy_id': 'strategy:repair_internal_links',
            'expected_value': 1.2,
            'strategy': {'recommendation_id': 'rec-1'},
            'simulation': {'simulation_id': 'sim-1', 'predicted_rank_delta': 1.1, 'confidence': 0.7},
        },
    )
    monkeypatch.setattr(pattern_processor, 'publish_event', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(simulation_processor, 'publish_event', lambda *_args, **_kwargs: None)

    pattern_processor.process({'campaign_id': 'campaign-a', 'features': {'f1': 1.0}})
    simulation_processor.process(
        {
            'campaign_id': 'campaign-a',
            'candidate_strategies': [{'strategy_id': 's1', 'strategy_actions': [{'type': 'internal_link', 'count': 1}]}],
        }
    )

    assert any(kind == 'pattern' for kind, _payload in updates)
    assert any(kind == 'simulation' for kind, _payload in updates)


def test_execution_processor_emits_started_and_completed(monkeypatch: Any) -> None:
    events: list[str] = []

    scheduled = SimpleNamespace(id='exec-1', campaign_id='campaign-z', status='scheduled')
    completed = SimpleNamespace(
        id='exec-1',
        campaign_id='campaign-z',
        status='completed',
        result_summary=json.dumps({'status': 'completed'}),
    )

    monkeypatch.setattr(execution_processor, 'SessionLocal', lambda: _FakeSession())
    monkeypatch.setattr(execution_processor, 'schedule_execution', lambda *_args, **_kwargs: scheduled)
    monkeypatch.setattr(execution_processor, 'execute_recommendation', lambda *_args, **_kwargs: completed)
    monkeypatch.setattr(execution_processor, 'publish_event', lambda event_type, _payload: events.append(event_type))

    result = execution_processor.process({'campaign_id': 'campaign-z', 'recommendation_id': 'rec-z'})

    assert result is not None
    assert EventType.EXECUTION_SCHEDULED.value in events
    assert EventType.EXECUTION_STARTED.value in events
    assert EventType.EXECUTION_COMPLETED.value in events


def test_outcome_processor_updates_graph(monkeypatch: Any) -> None:
    updates: list[dict[str, Any]] = []
    published: list[str] = []

    fake_execution = SimpleNamespace(id='exec-2', campaign_id='campaign-y', recommendation_id='rec-y')
    fake_outcome = SimpleNamespace(
        id='out-1',
        recommendation_id='rec-y',
        simulation_id='sim-2',
        delta=1.4,
        measured_at=SimpleNamespace(isoformat=lambda: '2026-03-06T00:00:00Z'),
    )

    class _FakeQuery:
        def filter(self, *_args: Any, **_kwargs: Any) -> '_FakeQuery':
            return self

        def order_by(self, *_args: Any, **_kwargs: Any) -> '_FakeQuery':
            return self

        def first(self) -> Any:
            return fake_outcome

    class _OutcomeSession(_FakeSession):
        def query(self, *_args: Any, **_kwargs: Any) -> _FakeQuery:
            return _FakeQuery()

    class _FakeUpdater:
        def update_from_outcome(self, payload: dict[str, Any]) -> list[str]:
            updates.append(payload)
            return ['o1']

    monkeypatch.setattr(outcome_processor, 'SessionLocal', lambda: _OutcomeSession())
    monkeypatch.setattr(outcome_processor, 'record_execution_result', lambda *_args, **_kwargs: fake_execution)
    monkeypatch.setattr(outcome_processor, 'get_graph_update_pipeline', lambda: _FakeUpdater())
    monkeypatch.setattr(outcome_processor, 'publish_event', lambda event_type, _payload: published.append(event_type))

    result = outcome_processor.process({'execution_id': 'exec-2', 'result': {'status': 'completed'}})

    assert result is not None
    assert updates
    assert published == [EventType.OUTCOME_RECORDED.value]
