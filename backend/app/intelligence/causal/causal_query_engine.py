from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.causal.causal_models import CausalPolicyPreference
from app.models.causal_edge import CausalEdge


def get_top_policies_for_feature(db: Session, feature: str, *, limit: int = 10) -> list[CausalPolicyPreference]:
    rows = (
        db.query(CausalEdge)
        .filter(
            CausalEdge.source_node == feature,
            CausalEdge.effect_size > 0,
        )
        .order_by(CausalEdge.confidence.desc(), CausalEdge.effect_size.desc(), CausalEdge.sample_size.desc(), CausalEdge.policy_id.asc())
        .limit(limit)
        .all()
    )
    return [_to_preference(row) for row in rows]


def get_policies_with_positive_effect(db: Session, industry: str, *, limit: int = 25) -> list[CausalPolicyPreference]:
    rows = (
        db.query(CausalEdge)
        .filter(
            CausalEdge.industry == industry,
            CausalEdge.effect_size > 0,
        )
        .order_by(CausalEdge.confidence.desc(), CausalEdge.effect_size.desc(), CausalEdge.sample_size.desc(), CausalEdge.policy_id.asc())
        .limit(limit)
        .all()
    )
    return [_to_preference(row) for row in rows]


def get_policies_with_high_confidence(
    db: Session,
    *,
    min_confidence: float = 0.7,
    industry: str | None = None,
    limit: int = 25,
) -> list[CausalPolicyPreference]:
    query = db.query(CausalEdge).filter(CausalEdge.confidence >= min_confidence)
    if industry is not None:
        query = query.filter(CausalEdge.industry == industry)
    rows = (
        query.order_by(CausalEdge.confidence.desc(), CausalEdge.effect_size.desc(), CausalEdge.sample_size.desc(), CausalEdge.policy_id.asc())
        .limit(limit)
        .all()
    )
    return [_to_preference(row) for row in rows]


def get_policy_preference_map(db: Session, industry: str) -> dict[str, CausalPolicyPreference]:
    preferences: dict[str, CausalPolicyPreference] = {}
    for row in get_policies_with_positive_effect(db, industry, limit=50):
        current = preferences.get(row.policy_id)
        if current is None or (row.confidence, row.effect_size, row.sample_size) > (
            current.confidence,
            current.effect_size,
            current.sample_size,
        ):
            preferences[row.policy_id] = row
    return preferences


def _to_preference(row: CausalEdge) -> CausalPolicyPreference:
    return CausalPolicyPreference(
        policy_id=row.policy_id,
        effect_size=float(row.effect_size),
        confidence=float(row.confidence),
        sample_size=int(row.sample_size),
        industry=row.industry,
    )
