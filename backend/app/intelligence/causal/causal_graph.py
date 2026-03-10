from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.causal.causal_models import CausalEdgeSnapshot
from app.models.causal_edge import CausalEdge


def upsert_causal_edge(db: Session, edge: CausalEdgeSnapshot) -> CausalEdge:
    existing = (
        db.query(CausalEdge)
        .filter(
            CausalEdge.source_node == edge.source_node,
            CausalEdge.target_node == edge.target_node,
            CausalEdge.policy_id == edge.policy_id,
            CausalEdge.industry == edge.industry,
        )
        .first()
    )
    if existing is None:
        row = CausalEdge(
            source_node=edge.source_node,
            target_node=edge.target_node,
            policy_id=edge.policy_id,
            effect_size=edge.effect_size,
            confidence=edge.confidence,
            sample_size=edge.sample_size,
            industry=edge.industry,
        )
        db.add(row)
        db.flush()
        return row

    previous_weight = max(int(existing.sample_size), 1)
    incoming_weight = max(int(edge.sample_size), 1)
    total_weight = previous_weight + incoming_weight
    existing.effect_size = round(
        ((float(existing.effect_size) * previous_weight) + (float(edge.effect_size) * incoming_weight)) / total_weight,
        6,
    )
    existing.confidence = round(
        min(
            1.0,
            ((float(existing.confidence) * previous_weight) + (float(edge.confidence) * incoming_weight)) / total_weight,
        ),
        6,
    )
    existing.sample_size = total_weight
    db.flush()
    return existing
