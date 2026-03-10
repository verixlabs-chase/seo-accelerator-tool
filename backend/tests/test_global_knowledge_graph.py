from __future__ import annotations

from app.intelligence.causal.causal_learning_engine import learn_from_experiment_completed
from app.intelligence.knowledge_graph.query_engine import (
    get_policies_with_high_confidence,
    get_policies_with_positive_effect,
    get_top_policies_for_feature,
)
from app.intelligence.portfolio.portfolio_engine import run_portfolio_cycle
from app.models.knowledge_graph import KnowledgeEdge, KnowledgeNode
from app.models.policy_performance import PolicyPerformance
from app.models.recommendation_outcome import RecommendationOutcome


def test_experiment_learning_updates_global_knowledge_graph(db_session) -> None:
    learn_from_experiment_completed(
        db_session,
        {
            'policy_id': 'policy-a',
            'effect_size': 0.4,
            'confidence': 0.8,
            'industry': 'unknown',
            'sample_size': 12,
            'source_node': 'internal_link_ratio',
            'target_node': 'outcome::success',
        },
    )
    db_session.commit()

    assert db_session.query(KnowledgeNode).filter(KnowledgeNode.node_type == 'policy', KnowledgeNode.node_key == 'policy-a').count() == 1
    assert db_session.query(KnowledgeNode).filter(KnowledgeNode.node_type == 'feature', KnowledgeNode.node_key == 'internal_link_ratio').count() == 1
    assert db_session.query(KnowledgeEdge).filter(KnowledgeEdge.edge_type == 'policy_feature').count() == 1
    assert db_session.query(KnowledgeEdge).filter(KnowledgeEdge.edge_type == 'feature_outcome').count() == 1
    assert db_session.query(KnowledgeEdge).filter(KnowledgeEdge.edge_type == 'policy_outcome').count() == 1


def test_global_knowledge_graph_queries_return_best_policies(db_session) -> None:
    for payload in [
        {
            'policy_id': 'policy-a',
            'effect_size': 0.25,
            'confidence': 0.95,
            'industry': 'local',
            'sample_size': 18,
            'source_node': 'internal_link_ratio',
            'target_node': 'outcome::success',
        },
        {
            'policy_id': 'policy-b',
            'effect_size': 0.55,
            'confidence': 0.85,
            'industry': 'local',
            'sample_size': 9,
            'source_node': 'internal_link_ratio',
            'target_node': 'outcome::success',
        },
        {
            'policy_id': 'policy-c',
            'effect_size': -0.1,
            'confidence': 0.99,
            'industry': 'local',
            'sample_size': 11,
            'source_node': 'content_growth_rate',
            'target_node': 'outcome::success',
        },
    ]:
        learn_from_experiment_completed(db_session, payload)
    db_session.commit()

    top_for_feature = get_top_policies_for_feature(db_session, 'internal_link_ratio', industry='local')
    positive = get_policies_with_positive_effect(db_session, 'local')
    high_confidence = get_policies_with_high_confidence(db_session, industry='local', min_confidence=0.9)

    assert [item.policy_id for item in top_for_feature] == ['policy-a', 'policy-b']
    assert [item.policy_id for item in positive[:2]] == ['policy-a', 'policy-b']
    assert [item.policy_id for item in high_confidence] == ['policy-c', 'policy-a']


def test_portfolio_engine_prefers_global_graph_policies(db_session, intelligence_graph, monkeypatch) -> None:
    monkeypatch.setattr(
        'app.intelligence.portfolio.portfolio_engine.apply_experiment_assignments',
        lambda db, campaign_id, industry, allocations: (allocations, []),
    )
    active_campaign = intelligence_graph['campaigns'][0]
    peer_campaign = intelligence_graph['campaigns'][1]
    recommendation = intelligence_graph['recommendations'][0]

    db_session.query(PolicyPerformance).delete()
    db_session.add_all(
        [
            PolicyPerformance(policy_id='parent-a', campaign_id=active_campaign.id, industry='unknown', success_score=0.1, execution_count=5, confidence=0.5),
            PolicyPerformance(policy_id='child-a', campaign_id=peer_campaign.id, industry='unknown', success_score=0.95, execution_count=4, confidence=0.4),
        ]
    )
    db_session.flush()

    learn_from_experiment_completed(
        db_session,
        {
            'policy_id': 'child-a',
            'effect_size': 0.8,
            'confidence': 0.95,
            'industry': 'local',
            'sample_size': 20,
            'source_node': 'internal_link_ratio',
            'target_node': 'outcome::success',
        },
    )
    db_session.flush()

    outcome = RecommendationOutcome(
        recommendation_id=recommendation.id,
        campaign_id=active_campaign.id,
        metric_before=100.0,
        metric_after=105.0,
        delta=5.0,
    )
    db_session.add(outcome)
    db_session.flush()

    result = run_portfolio_cycle(db_session, outcome)
    assert result is not None
    assert result.allocations
    assert 'child-a' in [item.policy_id for item in result.allocations]
