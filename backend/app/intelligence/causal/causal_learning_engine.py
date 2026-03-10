from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.causal.causal_models import ExperimentCompletedPayload
from app.intelligence.knowledge_graph.update_engine import update_global_knowledge_graph
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
    return edges['policy_outcome']
