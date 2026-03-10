from __future__ import annotations

from pathlib import Path

from app.intelligence.causal.causal_learning_engine import learn_from_experiment_completed
from app.intelligence.evolution.strategy_evolution_engine import evolve_strategies
from app.intelligence.portfolio.portfolio_engine import run_portfolio_cycle
from app.models.knowledge_graph import KnowledgeEdge, KnowledgeNode
from app.models.policy_performance import PolicyPerformance
from app.models.recommendation_outcome import RecommendationOutcome


ROOT = Path(__file__).resolve().parents[1] / 'app'
GRAPH_DIR = ROOT / 'intelligence' / 'knowledge_graph'


def test_causal_learning_updates_graph_edges(db_session) -> None:
    learn_from_experiment_completed(
        db_session,
        {
            'policy_id': 'policy-a',
            'effect_size': 0.4,
            'confidence': 0.8,
            'industry': 'local',
            'sample_size': 12,
            'source_node': 'internal_link_ratio',
            'target_node': 'outcome::success',
        },
    )
    db_session.commit()

    assert db_session.query(KnowledgeEdge).filter(KnowledgeEdge.edge_type == 'policy_feature').count() == 1
    assert db_session.query(KnowledgeEdge).filter(KnowledgeEdge.edge_type == 'feature_outcome').count() == 1
    assert db_session.query(KnowledgeEdge).filter(KnowledgeEdge.edge_type == 'policy_outcome').count() == 1


def test_policy_evolution_produces_policy_to_policy_edge(db_session, intelligence_graph) -> None:
    _ = intelligence_graph
    learn_from_experiment_completed(
        db_session,
        {
            'policy_id': 'increase_internal_links',
            'effect_size': 0.42,
            'confidence': 0.91,
            'sample_size': 18,
            'industry': 'local',
            'source_node': 'internal_link_ratio',
            'target_node': 'outcome::success',
        },
    )
    db_session.commit()

    result = evolve_strategies(db_session, industry='local', effect_threshold=0.2, confidence_threshold=0.7)
    db_session.commit()

    assert result.registered_policies
    edge = (
        db_session.query(KnowledgeEdge)
        .join(KnowledgeNode, KnowledgeEdge.source_node_id == KnowledgeNode.id)
        .filter(KnowledgeEdge.edge_type == 'policy_policy', KnowledgeNode.node_key == 'increase_internal_links')
        .first()
    )
    assert edge is not None


def test_portfolio_queries_graph_for_policy_selection(db_session, intelligence_graph, monkeypatch) -> None:
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


def test_architecture_guard_blocks_direct_knowledge_edge_writes() -> None:
    violations: list[str] = []
    for path in ROOT.rglob('*.py'):
        if GRAPH_DIR in path.parents:
            continue
        text = path.read_text(encoding='utf-8')
        direct_patterns = [
            'session.add(KnowledgeEdge',
            'db.add(KnowledgeEdge',
            'db.query(KnowledgeEdge).delete',
            'insert(KnowledgeEdge',
            'db.execute(insert(KnowledgeEdge',
        ]
        if any(pattern in text for pattern in direct_patterns):
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []
