from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.intelligence.outcome_tracker import record_outcome
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.intelligence import IntelligenceScore, StrategyRecommendation
from app.models.recommendation_outcome import RecommendationOutcome
from app.services import intelligence_service
from app.services.intelligence_runtime_service import recommendation_engine_source

_MEASURABLE_RECOMMENDATION_STATES = {
    "APPROVED",
    "SCHEDULED",
    "EXECUTED",
    "ROLLED_BACK",
}
_MATERIAL_DELTA = 0.01


def measure_recommendation_outcome(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    recommendation_id: str,
) -> tuple[RecommendationOutcome, bool]:
    recommendation = _tenant_recommendation(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        recommendation_id=recommendation_id,
    )
    if _status_value(recommendation.status) not in _MEASURABLE_RECOMMENDATION_STATES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose this recommendation before measuring its outcome",
        )

    previous_rows = (
        db.query(RecommendationOutcome)
        .filter(
            RecommendationOutcome.campaign_id == campaign_id,
            RecommendationOutcome.recommendation_id == recommendation_id,
        )
        .order_by(
            RecommendationOutcome.measured_at.desc(),
            RecommendationOutcome.id.desc(),
        )
        .all()
    )
    measurement_kinds = _measurement_kinds(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    previous_outcome = next(
        (
            row
            for row in previous_rows
            if measurement_kinds.get(row.id) == "opportunity_score"
        ),
        None,
    )
    baseline_score = _baseline_score(
        db,
        campaign_id=campaign_id,
        recommendation=recommendation,
        previous_outcome=previous_outcome,
    )
    current_score = intelligence_service.compute_score(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    if baseline_score is None:
        baseline_score = float(current_score.score_value)

    if (
        previous_outcome is not None
        and abs(float(previous_outcome.metric_after) - float(current_score.score_value))
        < _MATERIAL_DELTA
    ):
        return previous_outcome, False

    outcome = record_outcome(
        db,
        recommendation_id=recommendation_id,
        campaign_id=campaign_id,
        metric_before=baseline_score,
        metric_after=float(current_score.score_value),
        measurement_kind="opportunity_score",
        observation_only=True,
        emit_learning_event=True,
    )
    return outcome, True


def get_campaign_outcome_history(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    limit: int = 50,
) -> dict[str, Any]:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    rows = (
        db.query(RecommendationOutcome, StrategyRecommendation)
        .join(
            StrategyRecommendation,
            StrategyRecommendation.id == RecommendationOutcome.recommendation_id,
        )
        .filter(
            RecommendationOutcome.campaign_id == campaign_id,
            StrategyRecommendation.tenant_id == tenant_id,
            StrategyRecommendation.campaign_id == campaign_id,
        )
        .order_by(
            RecommendationOutcome.measured_at.desc(),
            RecommendationOutcome.id.desc(),
        )
        .limit(limit)
        .all()
    )
    measurement_kinds = _measurement_kinds(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    items = [
        _serialize_outcome(
            outcome,
            recommendation,
            measurement_kind=measurement_kinds.get(outcome.id, "legacy_metric"),
        )
        for outcome, recommendation in rows
    ]
    improved_count = sum(1 for item in items if item["direction"] == "improved")
    declined_count = sum(1 for item in items if item["direction"] == "declined")
    unchanged_count = sum(1 for item in items if item["direction"] == "no_material_change")
    score_items = [
        item for item in items if item["measurement_kind"] == "opportunity_score"
    ]
    average_delta = (
        round(sum(float(item["delta"]) for item in score_items) / len(score_items), 2)
        if score_items
        else 0.0
    )
    return {
        "campaign_id": campaign_id,
        "count": len(items),
        "summary": {
            "improved_count": improved_count,
            "declined_count": declined_count,
            "unchanged_count": unchanged_count,
            "average_score_delta": average_delta,
            "latest_measured_at": items[0]["measured_at"] if items else None,
        },
        "learning": {
            "state": "observation_only",
            "observations_recorded": len(items),
            "policy_updates_enabled": False,
            "causal_claims_allowed": False,
            "minimum_outcomes_before_review": 5,
        },
        "items": items,
    }


def _tenant_recommendation(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    recommendation_id: str,
) -> StrategyRecommendation:
    recommendation = (
        db.query(StrategyRecommendation)
        .join(Campaign, Campaign.id == StrategyRecommendation.campaign_id)
        .filter(
            StrategyRecommendation.id == recommendation_id,
            StrategyRecommendation.tenant_id == tenant_id,
            StrategyRecommendation.campaign_id == campaign_id,
            Campaign.tenant_id == tenant_id,
        )
        .first()
    )
    if recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recommendation not found",
        )
    return recommendation


def _baseline_score(
    db: Session,
    *,
    campaign_id: str,
    recommendation: StrategyRecommendation,
    previous_outcome: RecommendationOutcome | None,
) -> float | None:
    if previous_outcome is not None:
        return float(previous_outcome.metric_after)

    baseline = (
        db.query(IntelligenceScore)
        .filter(
            IntelligenceScore.campaign_id == campaign_id,
            IntelligenceScore.captured_at <= recommendation.created_at,
        )
        .order_by(IntelligenceScore.captured_at.desc(), IntelligenceScore.id.desc())
        .first()
    )
    if baseline is None:
        baseline = (
            db.query(IntelligenceScore)
            .filter(IntelligenceScore.campaign_id == campaign_id)
            .order_by(IntelligenceScore.captured_at.asc(), IntelligenceScore.id.asc())
            .first()
        )
    return float(baseline.score_value) if baseline is not None else None


def _measurement_kinds(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
) -> dict[str, str]:
    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.event_type == "recommendation.outcome_recorded",
            AuditLog.payload_json.like(f"%{campaign_id}%"),
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .all()
    )
    kinds: dict[str, str] = {}
    for row in rows:
        try:
            envelope = json.loads(row.payload_json or "{}")
        except json.JSONDecodeError:
            continue
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            continue
        outcome_id = str(payload.get("outcome_id") or "")
        if outcome_id and outcome_id not in kinds:
            kinds[outcome_id] = str(payload.get("measurement_kind") or "legacy_metric")
    return kinds


def _serialize_outcome(
    outcome: RecommendationOutcome,
    recommendation: StrategyRecommendation,
    *,
    measurement_kind: str,
) -> dict[str, Any]:
    delta = round(float(outcome.delta), 2)
    if measurement_kind == "opportunity_score":
        if delta > _MATERIAL_DELTA:
            direction = "improved"
        elif delta < -_MATERIAL_DELTA:
            direction = "declined"
        else:
            direction = "no_material_change"
    else:
        direction = "recorded_change" if abs(delta) > _MATERIAL_DELTA else "no_material_change"

    return {
        "id": outcome.id,
        "recommendation_id": outcome.recommendation_id,
        "recommendation_type": recommendation.recommendation_type,
        "recommendation_rationale": recommendation.rationale,
        "recommendation_status": _status_value(recommendation.status),
        "engine_source": recommendation_engine_source(recommendation),
        "measurement_kind": measurement_kind,
        "metric_label": (
            "Opportunity score"
            if measurement_kind == "opportunity_score"
            else "Recorded metric"
        ),
        "metric_before": round(float(outcome.metric_before), 2),
        "metric_after": round(float(outcome.metric_after), 2),
        "delta": delta,
        "direction": direction,
        "measured_at": _isoformat(outcome.measured_at),
        "causal_proof": False,
    }


def _isoformat(value: datetime) -> str:
    return value.isoformat()


def _status_value(value: object) -> str:
    enum_value = getattr(value, "value", None)
    return str(enum_value if enum_value is not None else value)
