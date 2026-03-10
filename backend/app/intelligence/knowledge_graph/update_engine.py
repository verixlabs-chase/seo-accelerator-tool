from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.metrics import graph_write_batch_size
from app.models.knowledge_graph import KnowledgeEdge, KnowledgeNode


@dataclass(slots=True)
class PendingEdgeWrite:
    source_node: KnowledgeNode
    target_node: KnowledgeNode
    edge_type: str
    industry: str
    effect_size: float
    confidence: float
    sample_size: int


class GraphWriteBatcher:
    def __init__(self) -> None:
        self._pending: list[PendingEdgeWrite] = []
        self._last_flush = monotonic()

    def enqueue(self, write: PendingEdgeWrite) -> None:
        self._pending.append(write)

    def flush(self, db: Session, *, force: bool = False) -> dict[tuple[str, str, str, str], KnowledgeEdge]:
        settings = get_settings()
        batch_size = max(1, int(settings.knowledge_graph_batch_size))
        flush_interval = max(1, int(settings.knowledge_graph_flush_interval_ms)) / 1000.0
        if not self._pending:
            return {}
        if not force and len(self._pending) < batch_size and (monotonic() - self._last_flush) < flush_interval:
            return {}

        pending = list(self._pending)
        self._pending.clear()
        self._last_flush = monotonic()
        graph_write_batch_size.set(len(pending))

        identities = {
            (item.source_node.id, item.target_node.id, item.edge_type, item.industry)
            for item in pending
        }
        existing_rows = (
            db.query(KnowledgeEdge)
            .filter(
                KnowledgeEdge.source_node_id.in_([item[0] for item in identities]),
                KnowledgeEdge.target_node_id.in_([item[1] for item in identities]),
                KnowledgeEdge.edge_type.in_([item[2] for item in identities]),
                KnowledgeEdge.industry.in_([item[3] for item in identities]),
            )
            .all()
            if identities
            else []
        )
        existing_map = {
            (row.source_node_id, row.target_node_id, row.edge_type, row.industry): row
            for row in existing_rows
        }

        new_rows: list[KnowledgeEdge] = []
        result: dict[tuple[str, str, str, str], KnowledgeEdge] = {}
        for item in pending:
            identity = (item.source_node.id, item.target_node.id, item.edge_type, item.industry)
            row = existing_map.get(identity)
            if row is None:
                row = KnowledgeEdge(
                    source_node_id=item.source_node.id,
                    target_node_id=item.target_node.id,
                    edge_type=item.edge_type,
                    industry=item.industry,
                    effect_size=item.effect_size,
                    confidence=item.confidence,
                    sample_size=item.sample_size,
                    updated_at=datetime.now(UTC),
                )
                new_rows.append(row)
                existing_map[identity] = row
            else:
                previous_weight = max(int(row.sample_size), 1)
                incoming_weight = max(int(item.sample_size), 1)
                total_weight = previous_weight + incoming_weight
                row.effect_size = round(
                    ((float(row.effect_size) * previous_weight) + (float(item.effect_size) * incoming_weight)) / total_weight,
                    6,
                )
                row.confidence = round(
                    min(
                        1.0,
                        ((float(row.confidence) * previous_weight) + (float(item.confidence) * incoming_weight)) / total_weight,
                    ),
                    6,
                )
                row.sample_size = total_weight
                row.updated_at = datetime.now(UTC)
            result[identity] = row

        if new_rows:
            db.add_all(new_rows)
        db.flush()
        return result


_BATCHER = GraphWriteBatcher()


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


def flush_graph_write_batch(db: Session, *, force: bool = False) -> dict[tuple[str, str, str, str], KnowledgeEdge]:
    return _BATCHER.flush(db, force=force)


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

    writes = {
        'policy_feature': PendingEdgeWrite(
            source_node=policy_node,
            target_node=feature_node,
            edge_type='policy_feature',
            industry=industry,
            effect_size=effect_size,
            confidence=confidence,
            sample_size=sample_size,
        ),
        'feature_outcome': PendingEdgeWrite(
            source_node=feature_node,
            target_node=outcome_node,
            edge_type='feature_outcome',
            industry=industry,
            effect_size=effect_size,
            confidence=confidence,
            sample_size=sample_size,
        ),
        'policy_outcome': PendingEdgeWrite(
            source_node=policy_node,
            target_node=outcome_node,
            edge_type='policy_outcome',
            industry=industry,
            effect_size=effect_size,
            confidence=confidence,
            sample_size=sample_size,
        ),
    }
    for item in writes.values():
        _BATCHER.enqueue(item)
    flushed = flush_graph_write_batch(db, force=True)
    return {
        name: flushed[(item.source_node.id, item.target_node.id, item.edge_type, item.industry)]
        for name, item in writes.items()
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
    write = PendingEdgeWrite(
        source_node=parent_node,
        target_node=child_node,
        edge_type='policy_policy',
        industry=industry,
        effect_size=effect_size,
        confidence=confidence,
        sample_size=1,
    )
    _BATCHER.enqueue(write)
    flushed = flush_graph_write_batch(db, force=True)
    return flushed[(parent_node.id, child_node.id, 'policy_policy', industry)]
