from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.strategy_memory_pattern import StrategyMemoryPattern

PROMOTION_MIN_SUPPORT = 10
PROMOTION_MIN_CONFIDENCE = 0.70


def record_validated_pattern(db: Session, pattern: dict[str, Any]) -> StrategyMemoryPattern | None:
    support_count = int(pattern.get('support_count', 0) or 0)
    confidence_score = float(pattern.get('confidence_score', pattern.get('confidence', 0.0)) or 0.0)

    if support_count < PROMOTION_MIN_SUPPORT or confidence_score < PROMOTION_MIN_CONFIDENCE:
        return None

    pattern_name = str(pattern.get('pattern_name', '') or '').strip()
    feature_name = str(pattern.get('feature_name', '') or '').strip()
    if not pattern_name or not feature_name:
        return None

    avg_outcome_delta = float(pattern.get('avg_outcome_delta', pattern.get('pattern_strength', 0.0)) or 0.0)
    description = str(
        pattern.get('pattern_description', f'Validated pattern for {pattern_name} on feature {feature_name}')
    )

    existing = (
        db.query(StrategyMemoryPattern)
        .filter(
            StrategyMemoryPattern.pattern_name == pattern_name,
            StrategyMemoryPattern.feature_name == feature_name,
        )
        .first()
    )

    if existing is None:
        row = StrategyMemoryPattern(
            pattern_name=pattern_name,
            feature_name=feature_name,
            pattern_description=description,
            support_count=support_count,
            avg_outcome_delta=avg_outcome_delta,
            confidence_score=confidence_score,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(row)
        db.flush()
        return row

    total_support = int(existing.support_count) + support_count
    combined_delta = ((existing.avg_outcome_delta * existing.support_count) + (avg_outcome_delta * support_count)) / max(total_support, 1)
    combined_confidence = max(existing.confidence_score, confidence_score)

    existing.pattern_description = description
    existing.support_count = total_support
    existing.avg_outcome_delta = round(combined_delta, 6)
    existing.confidence_score = round(combined_confidence, 6)
    existing.updated_at = datetime.now(UTC)
    db.flush()
    return existing


def update_pattern_statistics(db: Session, pattern_id: str, outcome_delta: float) -> StrategyMemoryPattern | None:
    row = db.get(StrategyMemoryPattern, pattern_id)
    if row is None:
        return None

    delta_value = float(outcome_delta)
    next_support = int(row.support_count) + 1
    next_avg = ((float(row.avg_outcome_delta) * int(row.support_count)) + delta_value) / max(next_support, 1)

    if delta_value > 0:
        confidence_shift = 0.01
    elif delta_value < 0:
        confidence_shift = -0.01
    else:
        confidence_shift = 0.0

    row.support_count = next_support
    row.avg_outcome_delta = round(next_avg, 6)
    row.confidence_score = round(max(0.0, min(1.0, float(row.confidence_score) + confidence_shift)), 6)
    row.updated_at = datetime.now(UTC)
    db.flush()
    return row
