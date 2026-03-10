from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.intelligence.global_graph.graph_schema import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    coerce_edge_type,
    coerce_node_type,
    validate_edge_metadata,
)
from app.models.intelligence_graph import IntelligenceGraphEdge, IntelligenceGraphNode


class GraphStoreProtocol(Protocol):
    def create_node(self, node_type: NodeType | str, node_id: str, metadata: dict[str, Any], session: Session | None = None) -> GraphNode:
        ...

    def get_node(self, node_id: str, session: Session | None = None) -> GraphNode | None:
        ...

    def upsert_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType | str,
        metadata: dict[str, Any],
        session: Session | None = None,
    ) -> GraphEdge:
        ...

    def get_edges(self, source_id: str, session: Session | None = None) -> list[GraphEdge]:
        ...

    def get_neighbors(self, node_id: str, session: Session | None = None) -> list[GraphNode]:
        ...

    def iter_edges(self, session: Session | None = None) -> list[GraphEdge]:
        ...


class InMemoryGraphStore:
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges_by_id: dict[str, GraphEdge] = {}
        self._edge_index: dict[tuple[str, str, str, str], str] = {}
        self._outgoing: dict[str, set[str]] = defaultdict(set)
        self._incoming: dict[str, set[str]] = defaultdict(set)

    def create_node(
        self,
        node_type: NodeType | str,
        node_id: str,
        metadata: dict[str, Any],
        session: Session | None = None,
    ) -> GraphNode:
        del session
        if not node_id:
            raise ValueError('node_id is required')

        resolved_node_type = coerce_node_type(node_type)
        now = datetime.now(UTC).isoformat()

        existing = self._nodes.get(node_id)
        if existing is None:
            node = GraphNode(
                node_id=node_id,
                node_type=resolved_node_type,
                metadata=dict(metadata or {}),
                created_at=now,
                updated_at=now,
            )
            self._nodes[node_id] = node
            return node

        if existing.node_type != resolved_node_type:
            raise ValueError(f'node_id {node_id} already exists with type {existing.node_type.value}')

        existing.metadata.update(dict(metadata or {}))
        existing.updated_at = now
        return existing

    def get_node(self, node_id: str, session: Session | None = None) -> GraphNode | None:
        del session
        return self._nodes.get(node_id)

    def upsert_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType | str,
        metadata: dict[str, Any],
        session: Session | None = None,
    ) -> GraphEdge:
        del session
        if source_id not in self._nodes:
            raise ValueError(f'Unknown source node: {source_id}')
        if target_id not in self._nodes:
            raise ValueError(f'Unknown target node: {target_id}')

        resolved_edge_type = coerce_edge_type(edge_type)
        incoming_metadata = validate_edge_metadata(metadata)

        cohort_context = incoming_metadata.get('cohort_context', {})
        cohort_key = _stable_json(cohort_context)

        edge_key = (source_id, target_id, resolved_edge_type.value, cohort_key)
        existing_edge_id = self._edge_index.get(edge_key)

        if existing_edge_id is None:
            edge_id = _deterministic_edge_id(source_id, target_id, resolved_edge_type.value, cohort_key)
            now = datetime.now(UTC).isoformat()
            edge = GraphEdge(
                edge_id=edge_id,
                source_id=source_id,
                target_id=target_id,
                edge_type=resolved_edge_type,
                metadata=incoming_metadata,
                created_at=now,
                updated_at=now,
            )
            self._edge_index[edge_key] = edge_id
            self._edges_by_id[edge_id] = edge
            self._outgoing[source_id].add(edge_id)
            self._incoming[target_id].add(edge_id)
            return edge

        edge = self._edges_by_id[existing_edge_id]
        edge.metadata = _merge_edge_metadata(edge.metadata, incoming_metadata)
        edge.updated_at = datetime.now(UTC).isoformat()
        return edge

    def get_edges(self, source_id: str, session: Session | None = None) -> list[GraphEdge]:
        del session
        edge_ids = sorted(self._outgoing.get(source_id, set()))
        return [self._edges_by_id[edge_id] for edge_id in edge_ids]

    def get_neighbors(self, node_id: str, session: Session | None = None) -> list[GraphNode]:
        del session
        neighbors: dict[str, GraphNode] = {}
        for edge_id in sorted(self._outgoing.get(node_id, set())):
            edge = self._edges_by_id[edge_id]
            neighbor = self._nodes.get(edge.target_id)
            if neighbor is not None:
                neighbors[neighbor.node_id] = neighbor
        return [neighbors[key] for key in sorted(neighbors)]

    def iter_edges(self, session: Session | None = None) -> list[GraphEdge]:
        del session
        return [self._edges_by_id[key] for key in sorted(self._edges_by_id)]


class PersistentGraphStore:
    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_node(
        self,
        node_type: NodeType | str,
        node_id: str,
        metadata: dict[str, Any],
        session: Session | None = None,
    ) -> GraphNode:
        if session is not None:
            return self._create_node(session, node_type, node_id, metadata)
        with self.session_scope() as managed:
            return self._create_node(managed, node_type, node_id, metadata)

    def get_node(self, node_id: str, session: Session | None = None) -> GraphNode | None:
        if session is not None:
            return self._get_node(session, node_id)
        with self.session_scope() as managed:
            return self._get_node(managed, node_id)

    def upsert_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType | str,
        metadata: dict[str, Any],
        session: Session | None = None,
    ) -> GraphEdge:
        if session is not None:
            return self._upsert_edge(session, source_id, target_id, edge_type, metadata)
        with self.session_scope() as managed:
            return self._upsert_edge(managed, source_id, target_id, edge_type, metadata)

    def get_edges(self, source_id: str, session: Session | None = None) -> list[GraphEdge]:
        if session is not None:
            return self._get_edges(session, source_id)
        with self.session_scope() as managed:
            return self._get_edges(managed, source_id)

    def get_neighbors(self, node_id: str, session: Session | None = None) -> list[GraphNode]:
        if session is not None:
            return self._get_neighbors(session, node_id)
        with self.session_scope() as managed:
            return self._get_neighbors(managed, node_id)

    def iter_edges(self, session: Session | None = None) -> list[GraphEdge]:
        if session is not None:
            return self._iter_edges(session)
        with self.session_scope() as managed:
            return self._iter_edges(managed)

    def _create_node(self, session: Session, node_type: NodeType | str, node_id: str, metadata: dict[str, Any]) -> GraphNode:
        if not node_id:
            raise ValueError('node_id is required')

        resolved_node_type = coerce_node_type(node_type)
        row = session.get(IntelligenceGraphNode, node_id)
        now = datetime.now(UTC)
        if row is None:
            row = IntelligenceGraphNode(
                node_id=node_id,
                node_type=resolved_node_type.value,
                metadata_json=dict(metadata or {}),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
        elif row.node_type != resolved_node_type.value:
            raise ValueError(f'node_id {node_id} already exists with type {row.node_type}')
        else:
            merged = dict(row.metadata_json or {})
            merged.update(dict(metadata or {}))
            row.metadata_json = merged
            row.updated_at = now
            session.flush()

        return _node_from_row(row)

    def _get_node(self, session: Session, node_id: str) -> GraphNode | None:
        row = session.get(IntelligenceGraphNode, node_id)
        return _node_from_row(row) if row is not None else None

    def _upsert_edge(
        self,
        session: Session,
        source_id: str,
        target_id: str,
        edge_type: EdgeType | str,
        metadata: dict[str, Any],
    ) -> GraphEdge:
        if session.get(IntelligenceGraphNode, source_id) is None:
            raise ValueError(f'Unknown source node: {source_id}')
        if session.get(IntelligenceGraphNode, target_id) is None:
            raise ValueError(f'Unknown target node: {target_id}')

        resolved_edge_type = coerce_edge_type(edge_type)
        incoming_metadata = validate_edge_metadata(metadata)
        cohort_key = _stable_json(dict(incoming_metadata.get('cohort_context') or {}))
        edge_id = _deterministic_edge_id(source_id, target_id, resolved_edge_type.value, cohort_key)
        row = session.get(IntelligenceGraphEdge, edge_id)
        now = datetime.now(UTC)

        if row is None:
            row = IntelligenceGraphEdge(
                edge_id=edge_id,
                source_id=source_id,
                target_id=target_id,
                edge_type=resolved_edge_type.value,
                metadata_json=incoming_metadata,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
        else:
            row.metadata_json = _merge_edge_metadata(dict(row.metadata_json or {}), incoming_metadata)
            row.updated_at = now
            session.flush()

        return _edge_from_row(row)

    def _get_edges(self, session: Session, source_id: str) -> list[GraphEdge]:
        rows = (
            session.query(IntelligenceGraphEdge)
            .filter(IntelligenceGraphEdge.source_id == source_id)
            .order_by(IntelligenceGraphEdge.edge_id.asc())
            .all()
        )
        return [_edge_from_row(row) for row in rows]

    def _get_neighbors(self, session: Session, node_id: str) -> list[GraphNode]:
        rows = (
            session.query(IntelligenceGraphNode)
            .join(IntelligenceGraphEdge, IntelligenceGraphEdge.target_id == IntelligenceGraphNode.node_id)
            .filter(IntelligenceGraphEdge.source_id == node_id)
            .order_by(IntelligenceGraphNode.node_id.asc())
            .all()
        )
        return [_node_from_row(row) for row in rows]

    def _iter_edges(self, session: Session) -> list[GraphEdge]:
        rows = session.query(IntelligenceGraphEdge).order_by(IntelligenceGraphEdge.edge_id.asc()).all()
        return [_edge_from_row(row) for row in rows]


def _merge_edge_metadata(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    existing_support = max(int(existing.get('support_count', 0)), 0)
    incoming_support = max(int(incoming.get('support_count', 0)), 0)
    total_support = existing_support + incoming_support

    if total_support > 0:
        merged_confidence = (
            (float(existing.get('confidence', 0.0)) * existing_support)
            + (float(incoming.get('confidence', 0.0)) * incoming_support)
        ) / total_support
        merged_strength = (
            (float(existing.get('outcome_strength', 0.0)) * existing_support)
            + (float(incoming.get('outcome_strength', 0.0)) * incoming_support)
        ) / total_support
    else:
        merged_confidence = max(float(existing.get('confidence', 0.0)), float(incoming.get('confidence', 0.0)))
        merged_strength = float(incoming.get('outcome_strength', existing.get('outcome_strength', 0.0)))

    merged = dict(existing)
    merged.update(incoming)
    merged['confidence'] = max(0.0, min(1.0, merged_confidence))
    merged['support_count'] = total_support
    merged['outcome_strength'] = merged_strength

    existing_timestamp = str(existing.get('timestamp', ''))
    incoming_timestamp = str(incoming.get('timestamp', ''))
    merged['timestamp'] = max(existing_timestamp, incoming_timestamp)

    existing_model = str(existing.get('model_version', ''))
    incoming_model = str(incoming.get('model_version', ''))
    merged['model_version'] = incoming_model or existing_model

    merged['cohort_context'] = dict(incoming.get('cohort_context') or existing.get('cohort_context') or {})
    return merged


def _deterministic_edge_id(source_id: str, target_id: str, edge_type: str, cohort_key: str) -> str:
    base = f'{source_id}|{edge_type}|{target_id}|{cohort_key}'
    return sha256(base.encode('utf-8')).hexdigest()


def _stable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload or {}, sort_keys=True, separators=(',', ':'))


def _node_from_row(row: IntelligenceGraphNode) -> GraphNode:
    return GraphNode(
        node_id=row.node_id,
        node_type=coerce_node_type(row.node_type),
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at.astimezone(UTC).isoformat(),
        updated_at=row.updated_at.astimezone(UTC).isoformat(),
    )


def _edge_from_row(row: IntelligenceGraphEdge) -> GraphEdge:
    return GraphEdge(
        edge_id=row.edge_id,
        source_id=row.source_id,
        target_id=row.target_id,
        edge_type=coerce_edge_type(row.edge_type),
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at.astimezone(UTC).isoformat(),
        updated_at=row.updated_at.astimezone(UTC).isoformat(),
    )
