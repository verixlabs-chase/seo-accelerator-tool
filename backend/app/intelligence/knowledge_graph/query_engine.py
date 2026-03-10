from __future__ import annotations

from sqlalchemy.orm import Session, aliased

from app.intelligence.knowledge_graph.knowledge_models import KnowledgePolicyPreference
from app.models.knowledge_graph import KnowledgeEdge, KnowledgeNode


_EDGE_TYPES = {
    'policy_feature': 'policy_feature',
    'feature_outcome': 'feature_outcome',
    'policy_outcome': 'policy_outcome',
}


def get_top_policies_for_feature(db: Session, feature: str, *, industry: str | None = None, limit: int = 10) -> list[KnowledgePolicyPreference]:
    source = aliased(KnowledgeNode)
    target = aliased(KnowledgeNode)
    query = (
        db.query(KnowledgeEdge, source)
        .join(source, KnowledgeEdge.source_node_id == source.id)
        .join(target, KnowledgeEdge.target_node_id == target.id)
        .filter(
            KnowledgeEdge.edge_type == _EDGE_TYPES['policy_feature'],
            target.node_type == 'feature',
            target.node_key == feature,
            source.node_type == 'policy',
            KnowledgeEdge.effect_size > 0,
        )
    )
    if industry is not None:
        query = query.filter(KnowledgeEdge.industry == industry)
    rows = query.order_by(KnowledgeEdge.confidence.desc(), KnowledgeEdge.effect_size.desc(), KnowledgeEdge.sample_size.desc(), source.node_key.asc()).limit(limit).all()
    return [_to_preference(edge, source.node_key) for edge, source in rows]


def get_policies_with_positive_effect(db: Session, industry: str, *, limit: int = 25) -> list[KnowledgePolicyPreference]:
    source = aliased(KnowledgeNode)
    rows = (
        db.query(KnowledgeEdge, source)
        .join(source, KnowledgeEdge.source_node_id == source.id)
        .filter(
            KnowledgeEdge.edge_type == _EDGE_TYPES['policy_outcome'],
            KnowledgeEdge.industry == industry,
            source.node_type == 'policy',
            KnowledgeEdge.effect_size > 0,
        )
        .order_by(KnowledgeEdge.confidence.desc(), KnowledgeEdge.effect_size.desc(), KnowledgeEdge.sample_size.desc(), source.node_key.asc())
        .limit(limit)
        .all()
    )
    return [_to_preference(edge, source.node_key) for edge, source in rows]


def get_policies_with_high_confidence(
    db: Session,
    *,
    min_confidence: float = 0.7,
    industry: str | None = None,
    limit: int = 25,
) -> list[KnowledgePolicyPreference]:
    source = aliased(KnowledgeNode)
    query = (
        db.query(KnowledgeEdge, source)
        .join(source, KnowledgeEdge.source_node_id == source.id)
        .filter(
            KnowledgeEdge.edge_type == _EDGE_TYPES['policy_outcome'],
            source.node_type == 'policy',
            KnowledgeEdge.confidence >= min_confidence,
        )
    )
    if industry is not None:
        query = query.filter(KnowledgeEdge.industry == industry)
    rows = query.order_by(KnowledgeEdge.confidence.desc(), KnowledgeEdge.effect_size.desc(), KnowledgeEdge.sample_size.desc(), source.node_key.asc()).limit(limit).all()
    return [_to_preference(edge, source.node_key) for edge, source in rows]


def get_policy_preference_map(db: Session, industry: str) -> dict[str, KnowledgePolicyPreference]:
    preferences: dict[str, KnowledgePolicyPreference] = {}
    for row in get_policies_with_positive_effect(db, industry, limit=50):
        current = preferences.get(row.policy_id)
        if current is None or (row.confidence, row.effect_size, row.sample_size) > (current.confidence, current.effect_size, current.sample_size):
            preferences[row.policy_id] = row
    return preferences


def _to_preference(edge: KnowledgeEdge, policy_id: str) -> KnowledgePolicyPreference:
    return KnowledgePolicyPreference(
        policy_id=policy_id,
        effect_size=float(edge.effect_size),
        confidence=float(edge.confidence),
        sample_size=int(edge.sample_size),
        industry=edge.industry,
    )
