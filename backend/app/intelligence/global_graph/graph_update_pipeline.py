from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from typing import Any

from app.intelligence.global_graph.graph_schema import EdgeType, NodeType
from app.intelligence.global_graph.graph_store import GraphStoreProtocol


class GraphUpdatePipeline:
    def __init__(self, store: GraphStoreProtocol) -> None:
        self.store = store

    def update_from_pattern(self, pattern: dict[str, Any]) -> list[str]:
        campaign_id = _require_id(pattern.get('campaign_id'), 'campaign_id')
        industry = _as_optional_text(pattern.get('industry'))
        model_version = _as_text(pattern.get('model_version') or 'pattern_engine_v1')
        timestamp = _as_text(pattern.get('detected_at') or datetime.now(UTC).isoformat())

        context = self.store.session_scope() if hasattr(self.store, 'session_scope') else nullcontext(None)
        with context as session:
            self.store.create_node(NodeType.CAMPAIGN, campaign_id, {'campaign_id': campaign_id}, session=session)
            if industry:
                self.store.create_node(NodeType.INDUSTRY, industry, {'industry': industry}, session=session)

            features = pattern.get('features') if isinstance(pattern.get('features'), dict) else {}
            patterns = pattern.get('patterns') if isinstance(pattern.get('patterns'), list) else []
            created_edges: list[str] = []

            for feature_key, feature_value in features.items():
                feature_id = _node_key(NodeType.FEATURE, str(feature_key))
                self.store.create_node(
                    NodeType.FEATURE,
                    feature_id,
                    {'feature_key': str(feature_key), 'value': feature_value},
                    session=session,
                )
                edge = self.store.upsert_edge(
                    campaign_id,
                    feature_id,
                    EdgeType.DERIVED_FROM,
                    _edge_metadata(
                        confidence=1.0,
                        support_count=1,
                        outcome_strength=0.0,
                        timestamp=timestamp,
                        model_version=model_version,
                        industry=industry,
                    ),
                    session=session,
                )
                created_edges.append(edge.edge_id)

            for item in patterns:
                if not isinstance(item, dict):
                    continue
                pattern_key = _as_optional_text(item.get('pattern_key'))
                if not pattern_key:
                    continue

                pattern_id = _node_key(NodeType.PATTERN, pattern_key)
                confidence = float(item.get('confidence', 0.6) or 0.6)
                evidence = item.get('evidence') if isinstance(item.get('evidence'), list) else []
                strategy_key = _as_optional_text(item.get('strategy_key'))

                self.store.create_node(
                    NodeType.PATTERN,
                    pattern_id,
                    {
                        'pattern_key': pattern_key,
                        'confidence': confidence,
                        'evidence': evidence,
                    },
                    session=session,
                )

                edge = self.store.upsert_edge(
                    campaign_id,
                    pattern_id,
                    EdgeType.DERIVED_FROM,
                    _edge_metadata(
                        confidence=1.0,
                        support_count=1,
                        outcome_strength=0.0,
                        timestamp=timestamp,
                        model_version=model_version,
                        industry=industry,
                    ),
                    session=session,
                )
                created_edges.append(edge.edge_id)

                for evidence_key in evidence:
                    feature_id = _node_key(NodeType.FEATURE, str(evidence_key))
                    self.store.create_node(NodeType.FEATURE, feature_id, {'feature_key': str(evidence_key)}, session=session)
                    edge = self.store.upsert_edge(
                        feature_id,
                        pattern_id,
                        EdgeType.CORRELATES_WITH,
                        _edge_metadata(
                            confidence=confidence,
                            support_count=1,
                            outcome_strength=0.0,
                            timestamp=timestamp,
                            model_version=model_version,
                            industry=industry,
                        ),
                        session=session,
                    )
                    created_edges.append(edge.edge_id)

                if strategy_key:
                    strategy_id = _node_key(NodeType.STRATEGY, strategy_key)
                    self.store.create_node(NodeType.STRATEGY, strategy_id, {'strategy_key': strategy_key}, session=session)
                    edge = self.store.upsert_edge(
                        strategy_id,
                        pattern_id,
                        EdgeType.DERIVED_FROM,
                        _edge_metadata(
                            confidence=confidence,
                            support_count=1,
                            outcome_strength=0.0,
                            timestamp=timestamp,
                            model_version=model_version,
                            industry=industry,
                        ),
                        session=session,
                    )
                    created_edges.append(edge.edge_id)

            return sorted(set(created_edges))

    def update_from_simulation(self, simulation: dict[str, Any]) -> list[str]:
        campaign_id = _require_id(simulation.get('campaign_id'), 'campaign_id')
        strategy_key = _as_optional_text(simulation.get('winning_strategy_id') or simulation.get('strategy_id'))
        if not strategy_key:
            return []

        industry = _as_optional_text(simulation.get('industry'))
        model_version = _as_text(simulation.get('model_version') or 'digital_twin_v1')
        timestamp = _as_text(simulation.get('timestamp') or datetime.now(UTC).isoformat())

        context = self.store.session_scope() if hasattr(self.store, 'session_scope') else nullcontext(None)
        with context as session:
            self.store.create_node(NodeType.CAMPAIGN, campaign_id, {'campaign_id': campaign_id}, session=session)
            if industry:
                self.store.create_node(NodeType.INDUSTRY, industry, {'industry': industry}, session=session)

            strategy_id = _node_key(NodeType.STRATEGY, strategy_key)
            self.store.create_node(NodeType.STRATEGY, strategy_id, {'strategy_key': strategy_key}, session=session)

            predicted_rank_delta = float(simulation.get('predicted_rank_delta', 0.0) or 0.0)
            outcome_id = _node_key(NodeType.OUTCOME, 'predicted_rank_change')
            self.store.create_node(
                NodeType.OUTCOME,
                outcome_id,
                {'outcome_key': 'predicted_rank_change', 'source': 'simulation'},
                session=session,
            )

            edge = self.store.upsert_edge(
                strategy_id,
                outcome_id,
                EdgeType.CORRELATES_WITH,
                _edge_metadata(
                    confidence=float(simulation.get('confidence', 0.65) or 0.65),
                    support_count=1,
                    outcome_strength=predicted_rank_delta,
                    timestamp=timestamp,
                    model_version=model_version,
                    industry=industry,
                ),
                session=session,
            )
            return [edge.edge_id]

    def update_from_outcome(self, outcome: dict[str, Any]) -> list[str]:
        campaign_id = _require_id(outcome.get('campaign_id'), 'campaign_id')
        strategy_key = _as_optional_text(outcome.get('strategy_id') or outcome.get('recommendation_id'))
        if not strategy_key:
            return []

        industry = _as_optional_text(outcome.get('industry'))
        model_version = _as_text(outcome.get('model_version') or 'outcome_tracker_v1')
        timestamp = _as_text(outcome.get('timestamp') or outcome.get('measured_at') or datetime.now(UTC).isoformat())

        context = self.store.session_scope() if hasattr(self.store, 'session_scope') else nullcontext(None)
        with context as session:
            self.store.create_node(NodeType.CAMPAIGN, campaign_id, {'campaign_id': campaign_id}, session=session)
            if industry:
                self.store.create_node(NodeType.INDUSTRY, industry, {'industry': industry}, session=session)

            strategy_id = _node_key(NodeType.STRATEGY, strategy_key)
            self.store.create_node(NodeType.STRATEGY, strategy_id, {'strategy_key': strategy_key}, session=session)

            outcome_key = _as_text(outcome.get('outcome_key') or outcome.get('outcome_id') or 'observed_rank_change')
            outcome_id = _node_key(NodeType.OUTCOME, outcome_key)
            self.store.create_node(NodeType.OUTCOME, outcome_id, {'outcome_key': outcome_key, 'source': 'observed'}, session=session)

            delta = float(outcome.get('delta', 0.0) or 0.0)
            confidence = float(outcome.get('confidence', 0.7) or 0.7)
            is_causal = bool(outcome.get('is_causal', False))

            if is_causal and confidence >= 0.75:
                edge_type = EdgeType.CAUSES
            elif delta > 0:
                edge_type = EdgeType.IMPROVES
            else:
                edge_type = EdgeType.CORRELATES_WITH

            edge = self.store.upsert_edge(
                strategy_id,
                outcome_id,
                edge_type,
                _edge_metadata(
                    confidence=confidence,
                    support_count=1,
                    outcome_strength=delta,
                    timestamp=timestamp,
                    model_version=model_version,
                    industry=industry,
                ),
                session=session,
            )
            return [edge.edge_id]


def _edge_metadata(
    *,
    confidence: float,
    support_count: int,
    outcome_strength: float,
    timestamp: str,
    model_version: str,
    industry: str | None,
) -> dict[str, Any]:
    cohort_context: dict[str, Any] = {}
    if industry:
        cohort_context['industry'] = industry

    return {
        'confidence': max(0.0, min(float(confidence), 1.0)),
        'support_count': max(0, int(support_count)),
        'outcome_strength': float(outcome_strength),
        'timestamp': str(timestamp),
        'model_version': str(model_version),
        'cohort_context': cohort_context,
    }


def _node_key(node_type: NodeType, key: str) -> str:
    normalized = key.strip().lower().replace(' ', '_')
    return f'{node_type.value}:{normalized}'


def _require_id(value: object, field_name: str) -> str:
    text = _as_optional_text(value)
    if not text:
        raise ValueError(f'{field_name} is required')
    return text


def _as_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _as_text(value: object) -> str:
    text = _as_optional_text(value)
    return text or ''
