from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.models.digital_twin_simulation import DigitalTwinSimulation
from app.models.recommendation_outcome import RecommendationOutcome
from app.schemas.digital_twin_simulation import DigitalTwinSimulationOut

router = APIRouter(prefix='/intelligence/simulations', tags=['intelligence'])


@router.get('/campaign/{campaign_id}')
def get_campaign_simulations(
    request: Request,
    campaign_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: dict = Depends(require_roles({'tenant_admin'})),
) -> dict:
    _ = user
    rows = (
        db.query(DigitalTwinSimulation)
        .filter(DigitalTwinSimulation.campaign_id == campaign_id)
        .order_by(DigitalTwinSimulation.created_at.desc(), DigitalTwinSimulation.id.desc())
        .limit(limit)
        .all()
    )

    simulation_ids = [row.id for row in rows]
    linked_outcomes: dict[str, RecommendationOutcome] = {}
    if simulation_ids:
        outcome_rows = (
            db.query(RecommendationOutcome)
            .filter(RecommendationOutcome.simulation_id.in_(simulation_ids))
            .order_by(RecommendationOutcome.measured_at.desc(), RecommendationOutcome.id.desc())
            .all()
        )
        for outcome in outcome_rows:
            if outcome.simulation_id and outcome.simulation_id not in linked_outcomes:
                linked_outcomes[str(outcome.simulation_id)] = outcome

    items = []
    for row in rows:
        payload = DigitalTwinSimulationOut.model_validate(row).model_dump(mode='json')
        outcome = linked_outcomes.get(row.id)
        if outcome is not None:
            actual_rank_delta = float(outcome.delta)
            actual_traffic_delta = float(outcome.delta)
            payload['actual_rank_delta'] = actual_rank_delta
            payload['actual_traffic_delta'] = actual_traffic_delta
            payload['prediction_error_rank'] = abs(float(row.predicted_rank_delta) - actual_rank_delta)
            payload['prediction_error_traffic'] = abs(float(row.predicted_traffic_delta) - actual_traffic_delta)
        items.append(payload)

    return envelope(
        request,
        {
            'campaign_id': campaign_id,
            'count': len(rows),
            'items': items,
        },
    )
