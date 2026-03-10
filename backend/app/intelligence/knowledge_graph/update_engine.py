from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.knowledge_graph import KnowledgeEdge, KnowledgeNode


def ensure_knowledge_node(db: Session, *, node_type: str, node_key: str, label: str | None = None) -> KnowledgeNode:
    existing = (
        db.query(KnowledgeNode)
        .filter(
            KnowledgeNode.node_type == node_type,
            KnowledgeNode.node_key == node_key,
        )
        .first()
    )
    if existing is not None:
        return existing

    row = KnowledgeNode(
        node_type=node_type,
        node_key=node_key,
        label=label or node_key,
    )
    db.add(row)
    db.flush()
    return row


def upsert_knowledge_edge(
    db: Session,
    *,
    source_node: KnowledgeNode,
    target_node: KnowledgeNode,
    edge_type: str,
    industry: str,
    effect_size: float,
    confidence: float,
    sample_size: int,
) -> KnowledgeEdge:
    existing = (
        db.query(KnowledgeEdge)
        .filter(
            KnowledgeEdge.source_node_id == source_node.id,
            KnowledgeEdge.target_node_id == target_node.id,
            KnowledgeEdge.edge_type == edge_type,
            KnowledgeEdge.industry == industry,
        )
        .first()
    )
    if existing is None:
        row = KnowledgeEdge(
            source_node_id=source_node.id,
            target_node_id=target_node.id,
            edge_type=edge_type,
            industry=industry,
            effect_size=effect_size,
            confidence=confidence,
            sample_size=sample_size,
        )
        db.add(row)
        db.flush()
        return row

    previous_weight = max(int(existing.sample_size), 1)
    incoming_weight = max(int(sample_size), 1)
    total_weight = previous_weight + incoming_weight
    existing.effect_size = round(
        ((float(existing.effect_size) * previous_weight) + (float(effect_size) * incoming_weight)) / total_weight,
        6,
    )
    existing.confidence = round(
        min(
            1.0,
            ((float(existing.confidence) * previous_weight) + (float(confidence) * incoming_weight)) / total_weight,
        ),
        6,
    )
    existing.sample_size = total_weight
    db.flush()
    return existing


def update_global_knowledge_graph(
    db: Session,
    *,
    policy_id: str,
    feature_key: str,
    outcome_key: str,
    industry: str,
    effect_size: float,
    confidence: float,
    sample_size: int,
) -> dict[str, KnowledgeEdge]:
    ensure_knowledge_node(db, node_type='industry', node_key=industry, label=industry)
    policy_node = ensure_knowledge_node(db, node_type='policy', node_key=policy_id, label=policy_id)
    feature_node = ensure_knowledge_node(db, node_type='feature', node_key=feature_key, label=feature_key)
    outcome_node = ensure_knowledge_node(db, node_type='outcome', node_key=outcome_key, label=outcome_key)

    return {
        'policy_feature': upsert_knowledge_edge(
            db,
            source_node=policy_node,
            target_node=feature_node,
            edge_type='policy_feature',
            industry=industry,
            effect_size=effect_size,
            confidence=confidence,
            sample_size=sample_size,
        ),
        'feature_outcome': upsert_knowledge_edge(
            db,
            source_node=feature_node,
            target_node=outcome_node,
            edge_type='feature_outcome',
            industry=industry,
            effect_size=effect_size,
            confidence=confidence,
            sample_size=sample_size,
        ),
        'policy_outcome': upsert_knowledge_edge(
            db,
            source_node=policy_node,
            target_node=outcome_node,
            edge_type='policy_outcome',
            industry=industry,
            effect_size=effect_size,
            confidence=confidence,
            sample_size=sample_size,
        ),
    }


def record_policy_evolution(
    db: Session,
    *,
    parent_policy: str,
    child_policy: str,
    industry: str,
    confidence: float,
    effect_size: float,
) -> KnowledgeEdge:
    parent_node = ensure_knowledge_node(db, node_type='policy', node_key=parent_policy, label=parent_policy)
    child_node = ensure_knowledge_node(db, node_type='policy', node_key=child_policy, label=child_policy)
    return upsert_knowledge_edge(
        db,
        source_node=parent_node,
        target_node=child_node,
        edge_type='policy_policy',
        industry=industry,
        effect_size=effect_size,
        confidence=confidence,
        sample_size=1,
    )
