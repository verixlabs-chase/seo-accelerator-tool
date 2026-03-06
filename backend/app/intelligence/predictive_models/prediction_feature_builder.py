from __future__ import annotations

from statistics import pvariance
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.feature_store import compute_features
from app.intelligence.global_graph.graph_service import get_graph_query_engine
from app.intelligence.industry_models.industry_query_engine import get_industry_query_engine
from app.models.recommendation_outcome import RecommendationOutcome


def build_prediction_features(campaign_id: str, strategy: dict[str, Any], db: Session | None = None) -> dict[str, float]:
    strategy_id = str(strategy.get('strategy_id', strategy.get('action', 'unknown_strategy')))
    industry_id = str(strategy.get('industry') or strategy.get('industry_id') or 'unknown').strip().lower().replace(' ', '_')

    campaign_features: dict[str, float] = {}
    if db is not None:
        try:
            campaign_features = compute_features(campaign_id, db=db, persist=False, publish=False)
        except Exception:
            campaign_features = {}

    momentum = float(campaign_features.get('ranking_velocity', 0.0) or 0.0)
    baseline_traffic = float(campaign_features.get('sessions', strategy.get('baseline_traffic', 0.0)) or strategy.get('baseline_traffic', 0.0) or 0.0)

    industry_engine = get_industry_query_engine()
    industry_success = industry_engine.get_strategy_success_rate(industry_id, strategy_id)

    graph_query = get_graph_query_engine()
    graph_rows = graph_query.get_relevant_strategies(
        campaign_id=campaign_id,
        industry=industry_id if industry_id != 'unknown' else None,
        top_k=max(10, int(strategy.get('graph_top_k', 10) or 10)),
        min_confidence=0.0,
    )

    graph_confidence_sum = 0.0
    graph_support = 0.0
    found = False
    for row in graph_rows:
        if str(row.get('strategy_id', '')) != strategy_id:
            continue
        found = True
        evidence = row.get('evidence') if isinstance(row.get('evidence'), list) else []
        graph_support += float(len(evidence))
        for item in evidence:
            try:
                graph_confidence_sum += float(item.get('confidence', 0.0))
            except (TypeError, ValueError, AttributeError):
                continue

    graph_confidence_avg = graph_confidence_sum / max(graph_support, 1.0) if found else 0.0

    historical_outcomes: list[float] = []
    if db is not None:
        try:
            rows = (
                db.query(RecommendationOutcome.delta)
                .filter(RecommendationOutcome.campaign_id == campaign_id)
                .order_by(RecommendationOutcome.measured_at.desc(), RecommendationOutcome.id.desc())
                .limit(50)
                .all()
            )
            historical_outcomes = [float(row.delta or 0.0) for row in rows]
        except Exception:
            historical_outcomes = []

    historical_outcome_delta = sum(historical_outcomes) / len(historical_outcomes) if historical_outcomes else 0.0
    outcome_variance = pvariance(historical_outcomes) if len(historical_outcomes) > 1 else 0.0
    sample_size = float(max(len(historical_outcomes), int(graph_support), 1))

    return {
        'campaign_momentum_score': round(momentum, 6),
        'baseline_traffic': round(baseline_traffic, 6),
        'industry_success_rate': round(float(industry_success), 6),
        'graph_confidence_avg': round(float(graph_confidence_avg), 6),
        'graph_support': round(float(graph_support), 6),
        'historical_outcome_delta': round(float(historical_outcome_delta), 6),
        'outcome_variance': round(float(outcome_variance), 6),
        'sample_size': round(float(sample_size), 6),
    }
