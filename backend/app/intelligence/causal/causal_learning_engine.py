from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.causal.causal_graph import upsert_causal_edge
from app.intelligence.knowledge_graph.update_engine import update_global_knowledge_graph
from app.intelligence.causal.causal_models import CausalEdgeSnapshot, ExperimentCompletedPayload
from app.models.causal_edge import CausalEdge


def learn_from_experiment_completed(db: Session, payload: dict[str, object] | ExperimentCompletedPayload) -> CausalEdge:
    message = payload if isinstance(payload, ExperimentCompletedPayload) else ExperimentCompletedPayload(**payload)
    source_node = message.source_node or f'industry::{message.industry}'
    target_node = message.target_node or 'outcome::success'
    update_global_knowledge_graph(
        db,
        policy_id=message.policy_id,
        feature_key=source_node,
        outcome_key=target_node,
        industry=message.industry,
        effect_size=message.effect_size,
        confidence=message.confidence,
        sample_size=message.sample_size,
    )
    edge = CausalEdgeSnapshot(
        source_node=source_node,
        target_node=target_node,
        policy_id=message.policy_id,
        effect_size=message.effect_size,
        confidence=message.confidence,
        sample_size=message.sample_size,
        industry=message.industry,
    )
    return upsert_causal_edge(db, edge)
