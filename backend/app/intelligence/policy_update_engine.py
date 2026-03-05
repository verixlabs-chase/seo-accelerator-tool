from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_outcome import RecommendationOutcome


def recommendation_effectiveness(db: Session) -> dict[str, dict[str, float]]:
    rows = (
        db.query(StrategyRecommendation.recommendation_type, RecommendationOutcome.delta)
        .join(RecommendationOutcome, RecommendationOutcome.recommendation_id == StrategyRecommendation.id)
        .all()
    )
    grouped: dict[str, list[float]] = defaultdict(list)
    for rec_type, delta in rows:
        grouped[str(rec_type)].append(float(delta))

    summary: dict[str, dict[str, float]] = {}
    for rec_type, deltas in grouped.items():
        samples = max(1, len(deltas))
        mean_delta = sum(deltas) / samples
        win_rate = sum(1 for item in deltas if item > 0) / samples
        summary[rec_type] = {
            'samples': float(samples),
            'mean_delta': round(mean_delta, 6),
            'win_rate': round(win_rate, 6),
        }
    return summary


def update_policy_weights(db: Session, base_weights: dict[str, float] | None = None) -> dict[str, float]:
    weights = dict(base_weights or {})
    effectiveness = recommendation_effectiveness(db)

    for rec_type, metrics in effectiveness.items():
        base = float(weights.get(rec_type, 1.0))
        mean_delta = float(metrics.get('mean_delta', 0.0))
        if mean_delta > 0:
            updated = base * 1.05
        elif mean_delta < 0:
            updated = base * 0.95
        else:
            updated = base
        weights[rec_type] = round(max(0.1, min(updated, 3.0)), 6)

    return weights
