from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.knowledge_graph.query_engine import (
    get_policy_preference_map as get_graph_policy_preference_map,
    get_policies_with_high_confidence as get_graph_policies_with_high_confidence,
    get_policies_with_positive_effect as get_graph_policies_with_positive_effect,
    get_top_policies_for_feature as get_graph_top_policies_for_feature,
)


def get_top_policies_for_feature(db: Session, feature: str, *, limit: int = 10):
    return get_graph_top_policies_for_feature(db, feature, limit=limit)


def get_policies_with_positive_effect(db: Session, industry: str, *, limit: int = 25):
    return get_graph_policies_with_positive_effect(db, industry, limit=limit)


def get_policies_with_high_confidence(
    db: Session,
    *,
    min_confidence: float = 0.7,
    industry: str | None = None,
    limit: int = 25,
):
    return get_graph_policies_with_high_confidence(db, min_confidence=min_confidence, industry=industry, limit=limit)


def get_policy_preference_map(db: Session, industry: str):
    return get_graph_policy_preference_map(db, industry)
