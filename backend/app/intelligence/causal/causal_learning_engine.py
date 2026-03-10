from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.causal.causal_graph import upsert_causal_edge
from app.intelligence.causal.causal_models import CausalEdgeSnapshot, ExperimentCompletedPayload
from app.models.causal_edge import CausalEdge


def learn_from_experiment_completed(db: Session, payload: dict[str, object] | ExperimentCompletedPayload) -> CausalEdge:
    message = payload if isinstance(payload, ExperimentCompletedPayload) else ExperimentCompletedPayload(**payload)
    source_node = message.source_node or f'industry::{message.industry}'
    target_node = message.target_node or 'outcome::success'
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
