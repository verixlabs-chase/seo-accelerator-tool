from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.models.causal_mechanism import FeatureImpactEdge, PolicyFeatureEdge


class PolicyFeatureEdgeSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')

    policy_id: str
    feature_name: str
    effect_size: float
    confidence: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=1)
    industry: str


class FeatureImpactEdgeSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')

    policy_id: str
    feature_name: str
    outcome_name: str = 'outcome::success'
    effect_size: float
    confidence: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=1)
    industry: str


def upsert_policy_feature_edge(db: Session, edge: PolicyFeatureEdgeSnapshot) -> PolicyFeatureEdge:
    row = (
        db.query(PolicyFeatureEdge)
        .filter(
            PolicyFeatureEdge.policy_id == edge.policy_id,
            PolicyFeatureEdge.feature_name == edge.feature_name,
            PolicyFeatureEdge.industry == edge.industry,
        )
        .first()
    )
    if row is None:
        row = PolicyFeatureEdge(**edge.model_dump(mode='python'))
        db.add(row)
        db.flush()
        return row

    _merge_weighted_values(row, effect_size=edge.effect_size, confidence=edge.confidence, sample_size=edge.sample_size)
    db.flush()
    return row


def upsert_feature_impact_edge(db: Session, edge: FeatureImpactEdgeSnapshot) -> FeatureImpactEdge:
    row = (
        db.query(FeatureImpactEdge)
        .filter(
            FeatureImpactEdge.policy_id == edge.policy_id,
            FeatureImpactEdge.feature_name == edge.feature_name,
            FeatureImpactEdge.outcome_name == edge.outcome_name,
            FeatureImpactEdge.industry == edge.industry,
        )
        .first()
    )
    if row is None:
        row = FeatureImpactEdge(**edge.model_dump(mode='python'))
        db.add(row)
        db.flush()
        return row

    _merge_weighted_values(row, effect_size=edge.effect_size, confidence=edge.confidence, sample_size=edge.sample_size)
    db.flush()
    return row


def _merge_weighted_values(row: PolicyFeatureEdge | FeatureImpactEdge, *, effect_size: float, confidence: float, sample_size: int) -> None:
    current_sample = int(row.sample_size)
    incoming_sample = max(1, int(sample_size))
    total_sample = current_sample + incoming_sample
    row.effect_size = round(((float(row.effect_size) * current_sample) + (float(effect_size) * incoming_sample)) / total_sample, 6)
    row.confidence = round(min(1.0, max(0.0, ((float(row.confidence) * current_sample) + (float(confidence) * incoming_sample)) / total_sample)), 6)
    row.sample_size = total_sample
