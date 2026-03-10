from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.intelligence.global_graph.graph_schema import EdgeType, NodeType
from app.intelligence.global_graph.graph_service import get_graph_store
from app.intelligence.industry_models.industry_query_engine import get_industry_query_engine
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.strategy_performance import StrategyPerformance


def analyze_strategy_performance(db: Session, *, industry: str | None = None) -> list[dict[str, Any]]:
    rows = (
        db.query(
            StrategyRecommendation.recommendation_type,
            func.avg(RecommendationOutcome.delta),
            func.count(RecommendationOutcome.id),
            func.max(RecommendationOutcome.measured_at),
            func.sum(case((RecommendationOutcome.delta > 0, 1), else_=0)),
        )
        .join(RecommendationOutcome, RecommendationOutcome.recommendation_id == StrategyRecommendation.id)
        .group_by(StrategyRecommendation.recommendation_type)
        .all()
    )

    industry_engine = get_industry_query_engine()
    summaries: list[dict[str, Any]] = []
    for recommendation_type, avg_delta, sample_size, last_outcome_at, win_count in rows:
        strategy_id = str(recommendation_type)
        graph_score = _strategy_graph_score(strategy_id, industry=industry)
        industry_prior = float(industry_engine.get_strategy_success_rate(industry, strategy_id)) if industry else 0.0
        sample_count = int(sample_size or 0)
        win_rate = 0.0 if sample_count <= 0 else float(win_count or 0) / float(sample_count)
        mean_delta = float(avg_delta or 0.0)
        normalized_delta = max(0.0, min(1.0, (mean_delta + 5.0) / 10.0))
        performance_score = round(max(0.0, min(1.0, win_rate * 0.45 + normalized_delta * 0.35 + graph_score * 0.1 + industry_prior * 0.1)), 6)
        lifecycle_stage = _lifecycle_stage(performance_score, sample_count)

        row = db.get(StrategyPerformance, strategy_id)
        previous_stage = row.lifecycle_stage if row is not None else 'candidate'
        if row is None:
            row = StrategyPerformance(strategy_id=strategy_id, recommendation_type=strategy_id)
            db.add(row)
        row.recommendation_type = strategy_id
        row.policy_id = _policy_id_from_recommendation_type(strategy_id)
        row.lifecycle_stage = lifecycle_stage
        row.performance_score = performance_score
        row.win_rate = round(win_rate, 6)
        row.avg_delta = round(mean_delta, 6)
        row.sample_size = sample_count
        row.graph_score = round(graph_score, 6)
        row.industry_prior = round(industry_prior, 6)
        row.last_outcome_at = _coerce_datetime(last_outcome_at)
        row.metadata_json = {
            **dict(row.metadata_json or {}),
            'industry': industry,
            'previous_stage': previous_stage,
        }
        row.last_updated = datetime.now(UTC)
        summaries.append(
            {
                'strategy_id': strategy_id,
                'recommendation_type': strategy_id,
                'policy_id': row.policy_id,
                'performance_score': performance_score,
                'win_rate': row.win_rate,
                'avg_delta': row.avg_delta,
                'sample_size': sample_count,
                'graph_score': row.graph_score,
                'industry_prior': row.industry_prior,
                'lifecycle_stage': lifecycle_stage,
            }
        )

    db.flush()
    return sorted(summaries, key=lambda item: (float(item['performance_score']), int(item['sample_size']), str(item['strategy_id'])), reverse=True)


def _strategy_graph_score(strategy_id: str, *, industry: str | None = None) -> float:
    strategy_node_id = _strategy_node_id(strategy_id)
    store = get_graph_store()
    score = 0.0
    support = 0.0
    for edge in store.get_edges(strategy_node_id):
        if edge.edge_type not in {EdgeType.IMPROVES, EdgeType.CAUSES, EdgeType.CORRELATES_WITH, EdgeType.DERIVED_FROM}:
            continue
        cohort = edge.metadata.get('cohort_context', {}) if isinstance(edge.metadata, dict) else {}
        if industry and str(cohort.get('industry', '')).strip().lower() not in {'', industry.strip().lower()}:
            continue
        confidence = float(edge.metadata.get('confidence', 0.0) or 0.0)
        outcome_strength = float(edge.metadata.get('outcome_strength', 0.0) or 0.0)
        support_count = float(edge.metadata.get('support_count', 1) or 1)
        score += max(0.0, confidence + max(outcome_strength, 0.0) * 0.2) * support_count
        support += support_count
    if support <= 0:
        return 0.0
    return max(0.0, min(1.0, score / max(support * 1.5, 1.0)))


def _strategy_node_id(strategy_id: str) -> str:
    return f'{NodeType.STRATEGY.value}:{strategy_id.strip().lower().replace(" ", "_")}'


def _lifecycle_stage(performance_score: float, sample_size: int) -> str:
    if sample_size < 3:
        return 'candidate'
    if performance_score >= 0.7:
        return 'promoted'
    if performance_score <= 0.35:
        return 'demoted'
    return 'active'


def _policy_id_from_recommendation_type(recommendation_type: str) -> str | None:
    if not recommendation_type.startswith('policy::'):
        return None
    parts = recommendation_type.split('::')
    return parts[1] if len(parts) > 1 else None


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return None
