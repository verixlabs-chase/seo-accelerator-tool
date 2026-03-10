from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.models.causal_mechanism import FeatureImpactEdge, PolicyFeatureEdge


class MechanismPolicyPreference(BaseModel):
    model_config = ConfigDict(extra='forbid')

    policy_id: str
    feature_name: str
    effect_size: float
    confidence: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=1)
    industry: str


class FeatureOutcomeInfluence(BaseModel):
    model_config = ConfigDict(extra='forbid')

    feature_name: str
    effect_size: float
    confidence: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=1)
    industry: str


def get_policies_affecting_feature(
    db: Session,
    feature: str,
    *,
    industry: str | None = None,
    limit: int = 10,
) -> list[MechanismPolicyPreference]:
    query = db.query(PolicyFeatureEdge).filter(
        PolicyFeatureEdge.feature_name == feature,
        PolicyFeatureEdge.effect_size > 0,
    )
    if industry is not None:
        query = query.filter(PolicyFeatureEdge.industry == industry)
    rows = (
        query.order_by(
            PolicyFeatureEdge.confidence.desc(),
            PolicyFeatureEdge.effect_size.desc(),
            PolicyFeatureEdge.sample_size.desc(),
            PolicyFeatureEdge.policy_id.asc(),
        )
        .limit(limit)
        .all()
    )
    return [
        MechanismPolicyPreference(
            policy_id=row.policy_id,
            feature_name=row.feature_name,
            effect_size=float(row.effect_size),
            confidence=float(row.confidence),
            sample_size=int(row.sample_size),
            industry=row.industry,
        )
        for row in rows
    ]


def get_features_most_influencing_outcome(
    db: Session,
    outcome: str,
    *,
    industry: str | None = None,
    limit: int = 10,
) -> list[FeatureOutcomeInfluence]:
    query = db.query(FeatureImpactEdge).filter(FeatureImpactEdge.outcome_name == outcome)
    if industry is not None:
        query = query.filter(FeatureImpactEdge.industry == industry)
    rows = query.order_by(
        FeatureImpactEdge.feature_name.asc(),
        FeatureImpactEdge.confidence.desc(),
        FeatureImpactEdge.sample_size.desc(),
        FeatureImpactEdge.policy_id.asc(),
    ).all()

    aggregates: dict[tuple[str, str], dict[str, float | int | str]] = {}
    for row in rows:
        key = (row.feature_name, row.industry)
        entry = aggregates.setdefault(
            key,
            {
                'feature_name': row.feature_name,
                'industry': row.industry,
                'weighted_effect': 0.0,
                'weighted_confidence': 0.0,
                'sample_size': 0,
            },
        )
        sample_size = max(1, int(row.sample_size))
        entry['weighted_effect'] = float(entry['weighted_effect']) + (float(row.effect_size) * sample_size)
        entry['weighted_confidence'] = float(entry['weighted_confidence']) + (float(row.confidence) * sample_size)
        entry['sample_size'] = int(entry['sample_size']) + sample_size

    influences: list[FeatureOutcomeInfluence] = []
    for entry in aggregates.values():
        sample_size = max(1, int(entry['sample_size']))
        influences.append(
            FeatureOutcomeInfluence(
                feature_name=str(entry['feature_name']),
                effect_size=round(float(entry['weighted_effect']) / sample_size, 6),
                confidence=round(float(entry['weighted_confidence']) / sample_size, 6),
                sample_size=sample_size,
                industry=str(entry['industry']),
            )
        )
    influences.sort(key=lambda item: (-item.effect_size, -item.confidence, -item.sample_size, item.feature_name))
    return influences[:limit]


def get_strategies_for_feature_improvement(
    db: Session,
    feature: str,
    *,
    industry: str | None = None,
    limit: int = 10,
) -> list[MechanismPolicyPreference]:
    return get_policies_affecting_feature(db, feature, industry=industry, limit=limit)
