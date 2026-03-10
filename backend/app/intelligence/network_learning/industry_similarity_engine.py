from __future__ import annotations

from datetime import UTC, datetime
from itertools import combinations_with_replacement
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.industry_models.industry_model_registry import get_registry
from app.models.industry_similarity_matrix import IndustrySimilarityMatrix

SIMILARITY_THRESHOLD = 0.6


def compute_industry_similarity_matrix(db: Session) -> list[dict[str, Any]]:
    registry = get_registry()
    industries = registry.list_industries(session=db)
    results: list[dict[str, Any]] = []
    for source, target in combinations_with_replacement(sorted(set(industries or ['unknown'])), 2):
        score = _similarity_score(registry.get_industry_model(source, session=db), registry.get_industry_model(target, session=db))
        for left, right in {(source, target), (target, source)}:
            key = f'{left}::{right}'
            row = db.get(IndustrySimilarityMatrix, key)
            if row is None:
                row = IndustrySimilarityMatrix(similarity_key=key, source_industry_id=left, target_industry_id=right)
                db.add(row)
            row.similarity_score = round(score, 6)
            row.transfer_allowed = 1.0 if score >= SIMILARITY_THRESHOLD else 0.0
            row.updated_at = datetime.now(UTC)
            results.append({'source_industry_id': left, 'target_industry_id': right, 'similarity_score': row.similarity_score, 'transfer_allowed': bool(row.transfer_allowed >= 1.0)})
    db.flush()
    return results


def similarity_allows_transfer(db: Session, source_industry_id: str, target_industry_id: str) -> bool:
    row = db.get(IndustrySimilarityMatrix, f'{_normalize(source_industry_id)}::{_normalize(target_industry_id)}')
    if row is None:
        return _normalize(source_industry_id) == _normalize(target_industry_id)
    return float(row.transfer_allowed or 0.0) >= 1.0


def _similarity_score(source: Any, target: Any) -> float:
    if source is None or target is None:
        return 1.0 if source is target else 0.0
    source_patterns = set((source.pattern_distribution or {}).keys())
    target_patterns = set((target.pattern_distribution or {}).keys())
    source_strategies = set((source.strategy_success_rates or {}).keys())
    target_strategies = set((target.strategy_success_rates or {}).keys())
    pattern_score = _jaccard(source_patterns, target_patterns)
    strategy_score = _jaccard(source_strategies, target_strategies)
    return max(0.0, min(1.0, pattern_score * 0.5 + strategy_score * 0.5))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _normalize(value: str) -> str:
    return str(value or 'unknown').strip().lower().replace(' ', '_') or 'unknown'
