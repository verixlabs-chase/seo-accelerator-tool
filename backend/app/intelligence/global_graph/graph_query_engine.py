from __future__ import annotations

from typing import Any

from app.intelligence.global_graph.graph_schema import EdgeType, NodeType
from app.intelligence.global_graph.graph_store import GraphStoreProtocol


class GraphQueryEngine:
    def __init__(self, store: GraphStoreProtocol) -> None:
        self.store = store

    def get_relevant_strategies(
        self,
        campaign_id: str,
        industry: str | None = None,
        top_k: int = 10,
        min_confidence: float = 0.0,
    ) -> list[dict[str, Any]]:
        if top_k <= 0:
            return []

        campaign = self.store.get_node(campaign_id)
        if campaign is None:
            return []
        if campaign.node_type != NodeType.CAMPAIGN:
            return []

        campaign_pattern_ids = self._campaign_pattern_ids(campaign_id)
        strategy_pattern_edges = self._pattern_to_strategy_edges(campaign_pattern_ids)

        scores: dict[str, float] = {}
        evidence: dict[str, list[dict[str, Any]]] = {}

        for edge in strategy_pattern_edges:
            strategy_id = edge.source_id
            if strategy_id not in scores:
                scores[strategy_id] = 0.0
                evidence[strategy_id] = []

            confidence = float(edge.metadata.get('confidence', 0.0))
            if confidence < min_confidence:
                continue

            pattern_score = confidence * 0.5
            scores[strategy_id] += pattern_score
            evidence[strategy_id].append(
                {
                    'edge_type': edge.edge_type.value,
                    'source_id': edge.source_id,
                    'target_id': edge.target_id,
                    'confidence': confidence,
                    'outcome_strength': float(edge.metadata.get('outcome_strength', 0.0)),
                    'support_count': int(edge.metadata.get('support_count', 0) or 0),
                }
            )

        for edge in self.store.iter_edges():
            if edge.source_id not in scores:
                continue
            if edge.edge_type not in {EdgeType.IMPROVES, EdgeType.CAUSES, EdgeType.CORRELATES_WITH}:
                continue

            confidence = float(edge.metadata.get('confidence', 0.0))
            if confidence < min_confidence:
                continue

            if not _industry_matches(edge.metadata, industry):
                continue

            support_count = max(int(edge.metadata.get('support_count', 0)), 1)
            strength = float(edge.metadata.get('outcome_strength', 0.0))
            relation_weight = 1.0
            if edge.edge_type == EdgeType.CAUSES:
                relation_weight = 1.2
            elif edge.edge_type == EdgeType.CORRELATES_WITH:
                relation_weight = 0.8

            outcome_score = confidence * relation_weight * strength * (1.0 + (support_count / 10.0))
            scores[edge.source_id] += outcome_score
            evidence[edge.source_id].append(
                {
                    'edge_type': edge.edge_type.value,
                    'source_id': edge.source_id,
                    'target_id': edge.target_id,
                    'confidence': confidence,
                    'outcome_strength': strength,
                    'support_count': support_count,
                }
            )

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        results: list[dict[str, Any]] = []
        for strategy_id, score in ranked[:top_k]:
            strategy_node = self.store.get_node(strategy_id)
            if strategy_node is None or strategy_node.node_type != NodeType.STRATEGY:
                continue
            results.append(
                {
                    'strategy_id': strategy_id,
                    'score': round(float(score), 6),
                    'evidence_count': len(evidence.get(strategy_id, [])),
                    'evidence': evidence.get(strategy_id, []),
                }
            )
        return results

    def _campaign_pattern_ids(self, campaign_id: str) -> set[str]:
        pattern_ids: set[str] = set()
        feature_ids: set[str] = set()

        for edge in self.store.get_edges(campaign_id):
            target = self.store.get_node(edge.target_id)
            if target is None:
                continue
            if target.node_type == NodeType.PATTERN:
                pattern_ids.add(target.node_id)
            elif target.node_type == NodeType.FEATURE:
                feature_ids.add(target.node_id)

        for edge in self.store.iter_edges():
            if edge.source_id in feature_ids and edge.edge_type == EdgeType.CORRELATES_WITH:
                target = self.store.get_node(edge.target_id)
                if target is not None and target.node_type == NodeType.PATTERN:
                    pattern_ids.add(target.node_id)

        return pattern_ids

    def _pattern_to_strategy_edges(self, pattern_ids: set[str]) -> list[Any]:
        matched = []
        if not pattern_ids:
            return matched

        for edge in self.store.iter_edges():
            if edge.edge_type != EdgeType.DERIVED_FROM:
                continue
            if edge.target_id not in pattern_ids:
                continue

            source = self.store.get_node(edge.source_id)
            if source is None or source.node_type != NodeType.STRATEGY:
                continue
            matched.append(edge)

        return matched


def _industry_matches(edge_metadata: dict[str, Any], industry: str | None) -> bool:
    if not industry:
        return True
    cohort_context = edge_metadata.get('cohort_context')
    if not isinstance(cohort_context, dict):
        return False
    return str(cohort_context.get('industry', '')).strip().lower() == industry.strip().lower()
