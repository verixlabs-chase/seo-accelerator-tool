from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class NodeType(str, Enum):
    CAMPAIGN = 'campaign'
    INDUSTRY = 'industry'
    FEATURE = 'feature'
    PATTERN = 'pattern'
    STRATEGY = 'strategy'
    OUTCOME = 'outcome'


class EdgeType(str, Enum):
    IMPROVES = 'improves'
    CORRELATES_WITH = 'correlates_with'
    CAUSES = 'causes'
    DERIVED_FROM = 'derived_from'


REQUIRED_EDGE_METADATA: tuple[str, ...] = (
    'confidence',
    'support_count',
    'outcome_strength',
    'timestamp',
    'model_version',
    'cohort_context',
)


@dataclass(slots=True)
class GraphNode:
    node_id: str
    node_type: NodeType
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(slots=True)
class GraphEdge:
    edge_id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    metadata: dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def coerce_node_type(node_type: NodeType | str) -> NodeType:
    if isinstance(node_type, NodeType):
        return node_type
    return NodeType(str(node_type).strip().lower())


def coerce_edge_type(edge_type: EdgeType | str) -> EdgeType:
    if isinstance(edge_type, EdgeType):
        return edge_type
    return EdgeType(str(edge_type).strip().lower())


def validate_edge_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(metadata or {})

    missing = [field for field in REQUIRED_EDGE_METADATA if field not in cleaned]
    if missing:
        raise ValueError(f'Missing required edge metadata: {missing}')

    confidence = float(cleaned['confidence'])
    support_count = int(cleaned['support_count'])
    outcome_strength = float(cleaned['outcome_strength'])
    timestamp = cleaned['timestamp']
    model_version = str(cleaned['model_version'])
    cohort_context = cleaned['cohort_context']

    if not isinstance(cohort_context, dict):
        raise ValueError('cohort_context must be a dict')

    if isinstance(timestamp, datetime):
        timestamp_value = timestamp.astimezone(UTC).isoformat()
    else:
        timestamp_value = str(timestamp)

    cleaned['confidence'] = max(0.0, min(confidence, 1.0))
    cleaned['support_count'] = max(support_count, 0)
    cleaned['outcome_strength'] = outcome_strength
    cleaned['timestamp'] = timestamp_value
    cleaned['model_version'] = model_version
    cleaned['cohort_context'] = dict(cohort_context)

    return cleaned
