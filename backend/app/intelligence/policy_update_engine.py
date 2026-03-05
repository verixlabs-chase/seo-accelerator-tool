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


def policy_effectiveness(db: Session) -> dict[str, dict[str, float]]:
    rows = (
        db.query(StrategyRecommendation.recommendation_type, RecommendationOutcome.delta)
        .join(RecommendationOutcome, RecommendationOutcome.recommendation_id == StrategyRecommendation.id)
        .all()
    )
    grouped: dict[str, list[float]] = defaultdict(list)

    for recommendation_type, delta in rows:
        policy_id = _policy_id_from_recommendation_type(str(recommendation_type))
        if policy_id is None:
            continue
        grouped[policy_id].append(float(delta))

    summary: dict[str, dict[str, float]] = {}
    for policy_id, deltas in grouped.items():
        samples = max(1, len(deltas))
        mean_delta = sum(deltas) / samples
        summary[policy_id] = {
            'samples': float(samples),
            'effectiveness': round(mean_delta, 6),
            'win_rate': round(sum(1 for item in deltas if item > 0) / samples, 6),
        }

    return summary


def update_policy_priority_weights(
    db: Session,
    base_policy_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    weights = dict(base_policy_weights or {})
    effectiveness = policy_effectiveness(db)

    for policy_id, metrics in effectiveness.items():
        base = float(weights.get(policy_id, 0.5))
        mean_effectiveness = float(metrics.get('effectiveness', 0.0))
        if mean_effectiveness > 0:
            updated = base * 1.05
        elif mean_effectiveness < 0:
            updated = base * 0.95
        else:
            updated = base
        weights[policy_id] = round(max(0.1, min(updated, 1.0)), 6)

    return weights


def _policy_id_from_recommendation_type(recommendation_type: str) -> str | None:
    if not recommendation_type.startswith('policy::'):
        return None
    parts = recommendation_type.split('::')
    if len(parts) < 2:
        return None
    return parts[1] or None
