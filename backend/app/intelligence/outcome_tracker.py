from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.events import emit_event
from app.models.campaign import Campaign
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
    measured_at: datetime | None = None,
    emit_learning_event: bool = True,
) -> RecommendationOutcome:
    before = float(metric_before)
    after = float(metric_after)
    row = RecommendationOutcome(
        recommendation_id=recommendation_id,
        campaign_id=campaign_id,
        metric_before=before,
        metric_after=after,
        delta=after - before,
        measured_at=measured_at or datetime.now(UTC),
    )
    db.add(row)
    db.flush()

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
                    'delta': row.delta,
                    'measured_at': row.measured_at.isoformat(),
                },
            )

    db.commit()
    db.refresh(row)
    return row
