from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.intelligence.global_graph.graph_schema import EdgeType, NodeType
from app.intelligence.global_graph.graph_service import get_graph_store
from app.intelligence.network_learning.industry_similarity_engine import similarity_allows_transfer
from app.models.seo_mutation_outcome import SEOMutationOutcome


def analyze_causal_outcomes(db: Session, *, target_industry_id: str | None = None) -> list[dict[str, Any]]:
    rows = (
        db.query(
            SEOMutationOutcome.mutation_type,
            SEOMutationOutcome.industry_id,
            func.avg(SEOMutationOutcome.rank_after - SEOMutationOutcome.rank_before),
            func.avg(SEOMutationOutcome.traffic_after - SEOMutationOutcome.traffic_before),
            func.count(SEOMutationOutcome.id),
        )
        .group_by(SEOMutationOutcome.mutation_type, SEOMutationOutcome.industry_id)
        .all()
    )
    graph_store = get_graph_store()
    findings: list[dict[str, Any]] = []
    for mutation_type, industry_id, avg_rank_change, avg_traffic_change, sample_size in rows:
        source_industry = str(industry_id or 'unknown')
        if target_industry_id and not similarity_allows_transfer(db, source_industry, target_industry_id):
            continue
        rank_improvement = -float(avg_rank_change or 0.0)
        traffic_improvement = float(avg_traffic_change or 0.0)
        confidence = max(0.0, min(1.0, float(sample_size or 0) / 25.0))
        causal_score = max(0.0, rank_improvement * 0.7 + traffic_improvement * 0.05)
        strategy_node = f'{NodeType.STRATEGY.value}:{str(mutation_type).strip().lower().replace(" ", "_")}'
        outcome_node = f'{NodeType.OUTCOME.value}:causal:{str(mutation_type).strip().lower().replace(" ", "_")}'
        graph_store.create_node(NodeType.STRATEGY, strategy_node, {'strategy_key': mutation_type, 'source': 'seo_flight_recorder'}, session=db)
        graph_store.create_node(NodeType.OUTCOME, outcome_node, {'outcome_key': 'causal_rank_improvement', 'industry': source_industry}, session=db)
        graph_store.upsert_edge(
            strategy_node,
            outcome_node,
            EdgeType.CAUSES if causal_score > 0 else EdgeType.CORRELATES_WITH,
            {
                'confidence': confidence,
                'support_count': int(sample_size or 0),
                'outcome_strength': causal_score,
                'timestamp': None,
                'model_version': 'causal_outcome_analyzer_v1',
                'cohort_context': {'industry': source_industry},
            },
            session=db,
        )
        findings.append({'mutation_type': str(mutation_type), 'industry_id': source_industry, 'causal_score': round(causal_score, 6), 'confidence': round(confidence, 6), 'sample_size': int(sample_size or 0)})
    db.flush()
    return sorted(findings, key=lambda item: (float(item['causal_score']), float(item['confidence']), int(item['sample_size'])), reverse=True)
