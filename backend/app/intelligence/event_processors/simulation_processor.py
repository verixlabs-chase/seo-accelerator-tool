from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.events.event_bus import publish_event
from app.events.event_types import EventType
from app.intelligence.digital_twin.strategy_optimizer import optimize_strategy
from app.intelligence.digital_twin.twin_state_model import DigitalTwinState
from app.intelligence.global_graph.graph_service import get_graph_update_pipeline


def process(payload: dict[str, object]) -> dict[str, object] | None:
    campaign_id = str(payload.get('campaign_id', '') or '')
    if not campaign_id:
        return None

    candidate_strategies = payload.get('candidate_strategies')
    if not isinstance(candidate_strategies, list) or not candidate_strategies:
        return None

    db = payload.get('db')
    if isinstance(db, Session):
        twin_state = DigitalTwinState.from_campaign_data(db, campaign_id)
        best = optimize_strategy(twin_state, candidate_strategies, db=db)
        if best is None:
            return None
        completion = _completion_payload(campaign_id, best)

        simulation_payload = dict(completion)
        simulation = simulation_payload.get('simulation')
        if isinstance(simulation, dict):
            simulation_payload.update(simulation)
        get_graph_update_pipeline().update_from_simulation(simulation_payload)

        publish_event(EventType.SIMULATION_COMPLETED.value, completion)
        return completion

    session = SessionLocal()
    try:
        twin_state = DigitalTwinState.from_campaign_data(session, campaign_id)
        best = optimize_strategy(twin_state, candidate_strategies, db=session)
        session.commit()
        if best is None:
            return None
        completion = _completion_payload(campaign_id, best)

        simulation_payload = dict(completion)
        simulation = simulation_payload.get('simulation')
        if isinstance(simulation, dict):
            simulation_payload.update(simulation)
        get_graph_update_pipeline().update_from_simulation(simulation_payload)

        publish_event(EventType.SIMULATION_COMPLETED.value, completion)
        return completion
    finally:
        session.close()


def _completion_payload(campaign_id: str, best: dict[str, object]) -> dict[str, object]:
    strategy = best.get('strategy') if isinstance(best.get('strategy'), dict) else {}
    simulation = best.get('simulation') if isinstance(best.get('simulation'), dict) else {}
    return {
        'campaign_id': campaign_id,
        'winning_strategy_id': best.get('strategy_id'),
        'expected_value': best.get('expected_value', 0.0),
        'simulation_id': simulation.get('simulation_id'),
        'simulation': simulation,
        'recommendation_id': strategy.get('recommendation_id'),
    }
