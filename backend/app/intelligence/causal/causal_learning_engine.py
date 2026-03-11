from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.causal.causal_models import ExperimentCompletedPayload
from app.intelligence.knowledge_graph.update_engine import ensure_knowledge_node, flush_graph_write_batch, update_global_knowledge_graph
from app.models.knowledge_graph import KnowledgeEdge


def learn_from_experiment_completed(db: Session, payload: dict[str, object] | ExperimentCompletedPayload) -> KnowledgeEdge:
    message = payload if isinstance(payload, ExperimentCompletedPayload) else ExperimentCompletedPayload(**payload)
    source_node = message.source_node or f'industry::{message.industry}'
    target_node = message.target_node or 'outcome::success'
    edges = update_global_knowledge_graph(
        db,
        policy_id=message.policy_id,
        feature_key=source_node,
        outcome_key=target_node,
        industry=message.industry,
        effect_size=message.effect_size,
        confidence=message.confidence,
        sample_size=message.sample_size,
    )
    if 'policy_outcome' not in edges:
        policy_node = ensure_knowledge_node(db, node_type='policy', node_key=message.policy_id, label=message.policy_id)
        outcome_node = ensure_knowledge_node(db, node_type='outcome', node_key=target_node, label=target_node)
        flushed = flush_graph_write_batch(db, force=True)
        return flushed[(policy_node.id, outcome_node.id, 'policy_outcome', message.industry)]
    return edges['policy_outcome']
