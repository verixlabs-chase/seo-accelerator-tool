from __future__ import annotations

from sqlalchemy.orm import aliased

from app.events import EventType, publish_event
from app.events.subscriber_registry import register_default_subscribers
from app.intelligence.causal.causal_learning_engine import learn_from_experiment_completed
from app.intelligence.causal.causal_query_engine import (
    get_policies_with_high_confidence,
    get_policies_with_positive_effect,
    get_top_policies_for_feature,
)
from app.intelligence.portfolio.portfolio_engine import run_portfolio_cycle
from app.models.knowledge_graph import KnowledgeEdge, KnowledgeNode
from app.models.policy_performance import PolicyPerformance
from app.models.recommendation_outcome import RecommendationOutcome


def test_experiment_completed_event_creates_causal_edge(db_session) -> None:
    register_default_subscribers(force_reset=True)

    publish_event(
        EventType.EXPERIMENT_COMPLETED.value,
        {
            'policy_id': 'policy-a',
            'effect_size': 0.4,
            'confidence': 0.8,
            'industry': 'unknown',
            'sample_size': 12,
            'source_node': 'industry::local',
            'target_node': 'outcome::success',
        },
    )

    policy = aliased(KnowledgeNode)
    target = aliased(KnowledgeNode)
    edge, policy_node, target_node = (
        db_session.query(KnowledgeEdge, policy, target)
        .join(policy, KnowledgeEdge.source_node_id == policy.id)
        .join(target, KnowledgeEdge.target_node_id == target.id)
        .filter(KnowledgeEdge.edge_type == 'policy_outcome', policy.node_key == 'policy-a')
        .one()
    )
    assert policy_node.node_key == 'policy-a'
    assert target_node.node_key == 'outcome::success'
    assert float(edge.effect_size) == 0.4
    assert float(edge.confidence) == 0.8
    assert int(edge.sample_size) == 12


def test_multiple_experiments_aggregate_existing_edge(db_session) -> None:
    learn_from_experiment_completed(
        db_session,
        {
            'policy_id': 'policy-a',
            'effect_size': 0.2,
            'confidence': 0.5,
            'industry': 'local',
            'sample_size': 10,
            'source_node': 'industry::local',
            'target_node': 'outcome::success',
        },
    )
    learn_from_experiment_completed(
        db_session,
        {
            'policy_id': 'policy-a',
            'effect_size': 0.8,
            'confidence': 0.9,
            'industry': 'local',
            'sample_size': 30,
            'source_node': 'industry::local',
            'target_node': 'outcome::success',
        },
    )
    db_session.commit()

    policy = aliased(KnowledgeNode)
    row = (
        db_session.query(KnowledgeEdge)
        .join(policy, KnowledgeEdge.source_node_id == policy.id)
        .filter(KnowledgeEdge.edge_type == 'policy_outcome', policy.node_key == 'policy-a')
        .one()
    )
    assert float(row.effect_size) == 0.65
    assert float(row.confidence) == 0.8
    assert int(row.sample_size) == 40


def test_query_engine_returns_expected_policies(db_session) -> None:
    for policy_id, effect_size, confidence, sample_size, source_node in [
        ('policy-a', 0.25, 0.95, 18, 'industry::local'),
        ('policy-b', 0.55, 0.85, 9, 'industry::local'),
        ('policy-c', -0.10, 0.99, 11, 'industry::local'),
        ('policy-d', 0.35, 0.65, 13, 'industry::local'),
    ]:
        learn_from_experiment_completed(
            db_session,
            {
                'policy_id': policy_id,
                'effect_size': effect_size,
                'confidence': confidence,
                'industry': 'local',
                'sample_size': sample_size,
                'source_node': source_node,
                'target_node': 'outcome::success',
            },
        )
    db_session.commit()

    top_for_feature = get_top_policies_for_feature(db_session, 'industry::local')
    positive = get_policies_with_positive_effect(db_session, 'local')
    high_confidence = get_policies_with_high_confidence(db_session, industry='local', min_confidence=0.9)

    assert [item.policy_id for item in top_for_feature[:3]] == ['policy-a', 'policy-b', 'policy-d']
    assert [item.policy_id for item in positive[:3]] == ['policy-a', 'policy-b', 'policy-d']
    assert [item.policy_id for item in high_confidence] == ['policy-c', 'policy-a']


def test_portfolio_engine_prefers_positive_high_confidence_causal_policies(db_session, intelligence_graph, monkeypatch) -> None:
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
            'industry': 'unknown',
            'sample_size': 20,
            'source_node': 'industry::local',
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
