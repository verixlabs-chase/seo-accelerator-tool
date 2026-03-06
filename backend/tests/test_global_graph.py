from __future__ import annotations

from app.intelligence.global_graph.graph_query_engine import GraphQueryEngine
from app.intelligence.global_graph.graph_schema import EdgeType, NodeType, validate_edge_metadata
from app.intelligence.global_graph.graph_store import InMemoryGraphStore
from app.intelligence.global_graph.graph_update_pipeline import GraphUpdatePipeline


def _base_metadata(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        'confidence': 0.7,
        'support_count': 1,
        'outcome_strength': 0.5,
        'timestamp': '2026-03-05T00:00:00Z',
        'model_version': 'test_v1',
        'cohort_context': {'industry': 'home_services'},
    }
    payload.update(overrides)
    return payload


def test_validate_edge_metadata_requires_fields() -> None:
    try:
        validate_edge_metadata({'confidence': 0.7})
        assert False, 'expected ValueError for missing metadata fields'
    except ValueError as exc:
        assert 'Missing required edge metadata' in str(exc)


def test_store_create_and_idempotent_edge_upsert() -> None:
    store = InMemoryGraphStore()
    campaign = store.create_node(NodeType.CAMPAIGN, 'campaign-1', {'name': 'Campaign 1'})
    strategy = store.create_node(NodeType.STRATEGY, 'strategy:internal_links', {'name': 'Internal Linking'})

    assert campaign.node_id == 'campaign-1'
    assert strategy.node_id == 'strategy:internal_links'
    assert store.get_node('campaign-1') is not None

    first = store.upsert_edge('strategy:internal_links', 'campaign-1', EdgeType.DERIVED_FROM, _base_metadata())
    second = store.upsert_edge('strategy:internal_links', 'campaign-1', EdgeType.DERIVED_FROM, _base_metadata())

    assert first.edge_id == second.edge_id
    assert second.metadata['support_count'] == 2
    assert len(store.get_edges('strategy:internal_links')) == 1
    assert [node.node_id for node in store.get_neighbors('strategy:internal_links')] == ['campaign-1']


def test_update_from_pattern_derives_expected_relationships() -> None:
    store = InMemoryGraphStore()
    pipeline = GraphUpdatePipeline(store)

    created = pipeline.update_from_pattern(
        {
            'campaign_id': 'campaign-1',
            'industry': 'home_services',
            'detected_at': '2026-03-05T10:00:00Z',
            'model_version': 'pattern_engine_v1',
            'features': {'internal_link_ratio': 0.4, 'ranking_velocity': -0.2},
            'patterns': [
                {
                    'pattern_key': 'internal_link_problem',
                    'confidence': 0.78,
                    'evidence': ['internal_link_ratio', 'ranking_velocity'],
                    'strategy_key': 'repair_internal_links',
                }
            ],
        }
    )

    assert created
    assert store.get_node('campaign-1') is not None
    assert store.get_node('feature:internal_link_ratio') is not None
    assert store.get_node('pattern:internal_link_problem') is not None
    assert store.get_node('strategy:repair_internal_links') is not None

    edges = store.iter_edges()
    relation_types = {edge.edge_type for edge in edges}
    assert EdgeType.DERIVED_FROM in relation_types
    assert EdgeType.CORRELATES_WITH in relation_types

    feature_to_pattern = [
        edge
        for edge in edges
        if edge.source_id == 'feature:internal_link_ratio' and edge.target_id == 'pattern:internal_link_problem'
    ]
    assert feature_to_pattern
    assert feature_to_pattern[0].edge_type == EdgeType.CORRELATES_WITH


def test_update_from_simulation_and_outcome() -> None:
    store = InMemoryGraphStore()
    pipeline = GraphUpdatePipeline(store)

    sim_edges = pipeline.update_from_simulation(
        {
            'campaign_id': 'campaign-2',
            'winning_strategy_id': 'topic_expansion',
            'industry': 'saas',
            'predicted_rank_delta': 1.7,
            'confidence': 0.66,
            'timestamp': '2026-03-05T12:00:00Z',
            'model_version': 'digital_twin_v2',
        }
    )
    out_edges = pipeline.update_from_outcome(
        {
            'campaign_id': 'campaign-2',
            'strategy_id': 'topic_expansion',
            'outcome_key': 'rank_position_change',
            'delta': 2.1,
            'confidence': 0.82,
            'is_causal': True,
            'industry': 'saas',
            'measured_at': '2026-03-05T15:00:00Z',
            'model_version': 'outcome_tracker_v1',
        }
    )

    assert sim_edges
    assert out_edges

    strategy_edges = store.get_edges('strategy:topic_expansion')
    edge_types = {edge.edge_type for edge in strategy_edges}
    assert EdgeType.CORRELATES_WITH in edge_types
    assert EdgeType.CAUSES in edge_types


def test_query_engine_returns_ranked_strategies() -> None:
    store = InMemoryGraphStore()
    pipeline = GraphUpdatePipeline(store)

    pipeline.update_from_pattern(
        {
            'campaign_id': 'campaign-3',
            'industry': 'home_services',
            'features': {'internal_link_ratio': 0.35},
            'patterns': [
                {
                    'pattern_key': 'internal_link_problem',
                    'confidence': 0.8,
                    'evidence': ['internal_link_ratio'],
                    'strategy_key': 'repair_internal_links',
                },
                {
                    'pattern_key': 'content_gap',
                    'confidence': 0.7,
                    'evidence': ['internal_link_ratio'],
                    'strategy_key': 'publish_cluster_content',
                },
            ],
        }
    )

    pipeline.update_from_outcome(
        {
            'campaign_id': 'campaign-3',
            'strategy_id': 'repair_internal_links',
            'outcome_key': 'rank_position_change',
            'delta': 2.5,
            'confidence': 0.9,
            'industry': 'home_services',
        }
    )
    pipeline.update_from_outcome(
        {
            'campaign_id': 'campaign-3',
            'strategy_id': 'publish_cluster_content',
            'outcome_key': 'rank_position_change',
            'delta': 0.8,
            'confidence': 0.7,
            'industry': 'home_services',
        }
    )

    engine = GraphQueryEngine(store)
    ranked = engine.get_relevant_strategies('campaign-3', industry='home_services', top_k=5)

    assert ranked
    assert ranked[0]['strategy_id'] == 'strategy:repair_internal_links'
    assert ranked[0]['score'] > ranked[1]['score']
