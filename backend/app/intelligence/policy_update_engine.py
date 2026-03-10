from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.intelligence import StrategyRecommendation
from app.models.policy_weights import PolicyWeight
from app.models.recommendation_outcome import RecommendationOutcome
from app.intelligence.strategy_evolution.strategy_lifecycle_manager import evolve_strategy_ecosystem as evolve_strategy_ecosystem_runtime


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
        base = float(weights.get(rec_type, _load_weight(db, f'recommendation::{rec_type}', 1.0)))
        mean_delta = float(metrics.get('mean_delta', 0.0))
        if mean_delta > 0:
            updated = base * 1.05
        elif mean_delta < 0:
            updated = base * 0.95
        else:
            updated = base
        bounded = round(max(0.1, min(updated, 3.0)), 6)
        weights[rec_type] = bounded
        _upsert_policy_weight(
            db,
            policy_id=f'recommendation::{rec_type}',
            weight=bounded,
            confidence=float(metrics.get('win_rate', 0.5) or 0.5),
            sample_size=int(metrics.get('samples', 0) or 0),
        )

    db.flush()
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


def update_policy_priority_weights(db: Session, base_policy_weights: dict[str, float] | None = None) -> dict[str, float]:
    weights = dict(base_policy_weights or {})
    effectiveness = policy_effectiveness(db)

    for policy_id, metrics in effectiveness.items():
        base = float(weights.get(policy_id, _load_weight(db, f'policy::{policy_id}', 0.5)))
        mean_effectiveness = float(metrics.get('effectiveness', 0.0))
        if mean_effectiveness > 0:
            updated = base * 1.05
        elif mean_effectiveness < 0:
            updated = base * 0.95
        else:
            updated = base
        bounded = round(max(0.1, min(updated, 1.0)), 6)
        weights[policy_id] = bounded
        _upsert_policy_weight(
            db,
            policy_id=f'policy::{policy_id}',
            weight=bounded,
            confidence=float(metrics.get('win_rate', 0.5) or 0.5),
            sample_size=int(metrics.get('samples', 0) or 0),
        )

    db.flush()
    return weights


def load_policy_weights(db: Session) -> dict[str, dict[str, float]]:
    rows = db.query(PolicyWeight).order_by(PolicyWeight.policy_id.asc()).all()
    return {
        row.policy_id: {
            'weight': float(row.weight),
            'confidence': float(row.confidence),
            'sample_size': int(row.sample_size),
        }
        for row in rows
    }


def _load_weight(db: Session, policy_id: str, fallback: float) -> float:
    row = db.get(PolicyWeight, policy_id)
    if row is None:
        return fallback
    return float(row.weight)


def _upsert_policy_weight(db: Session, *, policy_id: str, weight: float, confidence: float, sample_size: int) -> PolicyWeight:
    row = db.get(PolicyWeight, policy_id)
    if row is None:
        row = PolicyWeight(policy_id=policy_id)
        db.add(row)
    row.weight = float(weight)
    row.confidence = max(0.0, min(float(confidence), 1.0))
    row.sample_size = max(0, int(sample_size))
    row.last_updated = datetime.now(UTC)
    return row


def _policy_id_from_recommendation_type(recommendation_type: str) -> str | None:
    if not recommendation_type.startswith('policy::'):
        return None
    parts = recommendation_type.split('::')
    if len(parts) < 2:
        return None
    return parts[1] or None


def evolve_strategy_ecosystem(db: Session, *, industry: str | None = None) -> dict[str, object]:
    return evolve_strategy_ecosystem_runtime(db, industry=industry)
