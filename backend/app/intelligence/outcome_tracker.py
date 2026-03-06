from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.events import EventType, emit_event, publish_event
from app.models.campaign import Campaign
from app.models.digital_twin_simulation import DigitalTwinSimulation
from app.models.recommendation_execution import RecommendationExecution
from app.models.recommendation_outcome import RecommendationOutcome


def compute_reward(metric_before: float, metric_after: float) -> float:
    baseline = float(metric_before)
    current = float(metric_after)
    delta = current - baseline
    if baseline == 0:
        return max(-1.0, min(1.0, delta))
    ratio = delta / abs(baseline)
    return max(-1.0, min(1.0, ratio))


def record_outcome(
    db: Session,
    *,
    recommendation_id: str,
    campaign_id: str,
    metric_before: float,
    metric_after: float,
    simulation_id: str | None = None,
    measured_at: datetime | None = None,
    emit_learning_event: bool = True,
) -> RecommendationOutcome:
    before = float(metric_before)
    after = float(metric_after)
    row = RecommendationOutcome(
        recommendation_id=recommendation_id,
        campaign_id=campaign_id,
        simulation_id=simulation_id,
        metric_before=before,
        metric_after=after,
        delta=after - before,
        measured_at=measured_at or datetime.now(UTC),
    )
    db.add(row)
    db.flush()

    publish_event(
        EventType.OUTCOME_RECORDED.value,
        {
            'campaign_id': campaign_id,
            'recommendation_id': recommendation_id,
            'simulation_id': simulation_id,
            'outcome_id': row.id,
            'delta': row.delta,
            'measured_at': row.measured_at.isoformat(),
        },
    )

    if emit_learning_event:
        campaign = db.get(Campaign, campaign_id)
        if campaign is not None:
            emit_event(
                db,
                tenant_id=campaign.tenant_id,
                event_type='recommendation.outcome_recorded',
                payload={
                    'campaign_id': campaign_id,
                    'recommendation_id': recommendation_id,
                    'simulation_id': simulation_id,
                    'delta': row.delta,
                    'measured_at': row.measured_at.isoformat(),
                },
            )

    db.commit()
    db.refresh(row)
    return row


def record_execution_outcome(
    db: Session,
    *,
    execution: RecommendationExecution,
    metric_before: float,
    metric_after: float,
) -> RecommendationOutcome:
    simulation_id = _resolve_simulation_for_execution(db, execution)
    return record_outcome(
        db,
        recommendation_id=execution.recommendation_id,
        campaign_id=execution.campaign_id,
        simulation_id=simulation_id,
        metric_before=metric_before,
        metric_after=metric_after,
        emit_learning_event=True,
    )


def _resolve_simulation_for_execution(db: Session, execution: RecommendationExecution) -> str | None:
    reference_time = execution.created_at or datetime.now(UTC)
    row = (
        db.query(DigitalTwinSimulation)
        .filter(
            DigitalTwinSimulation.campaign_id == execution.campaign_id,
            DigitalTwinSimulation.selected_strategy.is_(True),
            DigitalTwinSimulation.created_at <= reference_time,
        )
        .order_by(DigitalTwinSimulation.created_at.desc(), DigitalTwinSimulation.id.desc())
        .first()
    )
    if row is not None:
        return row.id

    fallback = (
        db.query(DigitalTwinSimulation)
        .filter(
            DigitalTwinSimulation.campaign_id == execution.campaign_id,
            DigitalTwinSimulation.selected_strategy.is_(True),
        )
        .order_by(DigitalTwinSimulation.created_at.desc(), DigitalTwinSimulation.id.desc())
        .first()
    )
    return fallback.id if fallback is not None else None
