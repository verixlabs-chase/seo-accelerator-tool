from __future__ import annotations

from typing import Any

from app.intelligence.strategy_transfer_engine import transfer_strategies


class _FakeQueryEngine:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get_relevant_strategies(
        self,
        campaign_id: str,
        industry: str | None = None,
        top_k: int = 10,
        min_confidence: float = 0.0,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                'campaign_id': campaign_id,
                'industry': industry,
                'top_k': top_k,
                'min_confidence': min_confidence,
            }
        )
        return [
            {
                'strategy_id': 'strategy:repair_internal_links',
                'score': 5.4,
                'evidence': [
                    {
                        'confidence': 0.9,
                        'support_count': 4,
                        'outcome_strength': 2.4,
                    }
                ],
            },
            {
                'strategy_id': 'strategy:publish_cluster_content',
                'score': 3.1,
                'evidence': [
                    {
                        'confidence': 0.7,
                        'support_count': 2,
                        'outcome_strength': 1.3,
                    }
                ],
            },
        ]


def test_transfer_strategies_retrieves_from_graph() -> None:
    query = _FakeQueryEngine()

    payload = transfer_strategies(
        'campaign-1',
        query_engine=query,
        twin_state_builder=lambda _db, _campaign_id: object(),
        simulate_fn=lambda _twin_state, _actions, **_kwargs: {'confidence': 0.5, 'expected_value': 0.5},
    )

    assert len(query.calls) == 1
    assert query.calls[0]['campaign_id'] == 'campaign-1'
    assert len(payload['strategies']) == 2


def test_transfer_strategies_passes_candidates_to_simulation() -> None:
    query = _FakeQueryEngine()
    simulated: list[dict[str, Any]] = []

    def fake_simulator(_twin_state: object, actions: list[dict[str, object]], **kwargs: Any) -> dict[str, Any]:
        simulated.append({'actions': actions, 'strategy_id': kwargs.get('strategy_id')})
        return {
            'strategy_id': kwargs.get('strategy_id'),
            'confidence': 0.6,
            'expected_value': 1.2,
        }

    transfer_strategies(
        'campaign-2',
        query_engine=query,
        twin_state_builder=lambda _db, _campaign_id: object(),
        simulate_fn=fake_simulator,
    )

    assert len(simulated) == 2
    strategy_ids = sorted(str(item['strategy_id']) for item in simulated)
    assert strategy_ids == ['strategy:publish_cluster_content', 'strategy:repair_internal_links']

    action_types = {str(item['actions'][0]['type']) for item in simulated}
    assert 'internal_link' in action_types
    assert 'publish_content' in action_types


def test_transfer_strategies_returns_confidence_sorted_results() -> None:
    query = _FakeQueryEngine()

    def fake_simulator(_twin_state: object, _actions: list[dict[str, object]], **kwargs: Any) -> dict[str, Any]:
        strategy_id = str(kwargs.get('strategy_id'))
        if strategy_id.endswith('publish_cluster_content'):
            return {'strategy_id': strategy_id, 'confidence': 0.55, 'expected_value': 1.0}
        return {'strategy_id': strategy_id, 'confidence': 0.91, 'expected_value': 0.8}

    payload = transfer_strategies(
        'campaign-3',
        query_engine=query,
        twin_state_builder=lambda _db, _campaign_id: object(),
        simulate_fn=fake_simulator,
    )

    strategy_ids = [str(item['strategy_id']) for item in payload['strategies']]
    assert strategy_ids == ['strategy:repair_internal_links', 'strategy:publish_cluster_content']
    assert payload['confidence_scores'] == [0.91, 0.55]
