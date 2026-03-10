from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.intelligence.causal_mechanisms.mechanism_graph import (
    FeatureImpactEdgeSnapshot,
    PolicyFeatureEdgeSnapshot,
    upsert_feature_impact_edge,
    upsert_policy_feature_edge,
)
from app.models.experiment import ExperimentOutcome
from app.models.temporal import TemporalSignalSnapshot

_FEATURE_SOURCE = 'feature_store_v1'


class MechanismExperimentPayload(BaseModel):
    model_config = ConfigDict(extra='allow')

    policy_id: str
    effect_size: float
    confidence: float = Field(ge=0.0, le=1.0)
    industry: str
    sample_size: int = Field(default=1, ge=1)
    campaign_id: str | None = None
    experiment_id: str | None = None
    outcome_id: str | None = None
    measured_at: datetime | None = None
    outcome_name: str = 'outcome::success'


class LearnedMechanismResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    policy_feature_edges: list[str]
    feature_impact_edges: list[str]
    feature_deltas: dict[str, float]


def learn_mechanisms_from_experiment_completed(
    db: Session,
    payload: dict[str, object] | MechanismExperimentPayload,
) -> LearnedMechanismResult:
    message = payload if isinstance(payload, MechanismExperimentPayload) else MechanismExperimentPayload(**payload)
    context = _resolve_context(db, message)
    if context is None:
        return LearnedMechanismResult(policy_feature_edges=[], feature_impact_edges=[], feature_deltas={})

    campaign_id, measured_at = context
    baseline = _feature_snapshot_map(db, campaign_id=campaign_id, measured_at=measured_at, before=True)
    followup = _feature_snapshot_map(db, campaign_id=campaign_id, measured_at=measured_at, before=False)

    policy_feature_edges: list[str] = []
    feature_impact_edges: list[str] = []
    deltas: dict[str, float] = {}
    for feature_name in sorted(set(baseline).intersection(followup)):
        delta = round(float(followup[feature_name].metric_value) - float(baseline[feature_name].metric_value), 6)
        if abs(delta) < 1e-9:
            continue
        deltas[feature_name] = delta
        snapshot_confidence = round((float(baseline[feature_name].confidence) + float(followup[feature_name].confidence)) / 2.0, 6)
        edge_confidence = min(float(message.confidence), snapshot_confidence)
        policy_feature = upsert_policy_feature_edge(
            db,
            PolicyFeatureEdgeSnapshot(
                policy_id=message.policy_id,
                feature_name=feature_name,
                effect_size=delta,
                confidence=edge_confidence,
                sample_size=message.sample_size,
                industry=message.industry,
            ),
        )
        impact = upsert_feature_impact_edge(
            db,
            FeatureImpactEdgeSnapshot(
                policy_id=message.policy_id,
                feature_name=feature_name,
                outcome_name=message.outcome_name,
                effect_size=round(delta * float(message.effect_size), 6),
                confidence=edge_confidence,
                sample_size=message.sample_size,
                industry=message.industry,
            ),
        )
        policy_feature_edges.append(policy_feature.id)
        feature_impact_edges.append(impact.id)

    return LearnedMechanismResult(
        policy_feature_edges=policy_feature_edges,
        feature_impact_edges=feature_impact_edges,
        feature_deltas=deltas,
    )


def _resolve_context(db: Session, message: MechanismExperimentPayload) -> tuple[str, datetime] | None:
    if message.campaign_id and message.measured_at:
        measured_at = message.measured_at
        if measured_at.tzinfo is None:
            measured_at = measured_at.replace(tzinfo=UTC)
        return message.campaign_id, measured_at

    query = db.query(ExperimentOutcome)
    if message.outcome_id:
        row = query.filter(ExperimentOutcome.outcome_id == message.outcome_id).order_by(ExperimentOutcome.measured_at.desc()).first()
        if row is not None:
            return row.campaign_id, row.measured_at
    if message.experiment_id:
        row = query.filter(ExperimentOutcome.experiment_id == message.experiment_id).order_by(ExperimentOutcome.measured_at.desc()).first()
        if row is not None:
            return row.campaign_id, row.measured_at
    return None


def _feature_snapshot_map(db: Session, *, campaign_id: str, measured_at: datetime, before: bool) -> dict[str, TemporalSignalSnapshot]:
    query = db.query(TemporalSignalSnapshot).filter(
        TemporalSignalSnapshot.campaign_id == campaign_id,
        TemporalSignalSnapshot.source == _FEATURE_SOURCE,
    )
    if before:
        rows = (
            query.filter(TemporalSignalSnapshot.observed_at <= measured_at)
            .order_by(TemporalSignalSnapshot.metric_name.asc(), TemporalSignalSnapshot.observed_at.desc(), TemporalSignalSnapshot.id.desc())
            .all()
        )
    else:
        rows = (
            query.filter(TemporalSignalSnapshot.observed_at >= measured_at)
            .order_by(TemporalSignalSnapshot.metric_name.asc(), TemporalSignalSnapshot.observed_at.asc(), TemporalSignalSnapshot.id.asc())
            .all()
        )
    snapshots: dict[str, TemporalSignalSnapshot] = {}
    for row in rows:
        snapshots.setdefault(row.metric_name, row)
    return snapshots
