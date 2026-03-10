from __future__ import annotations

from app.db.session import SessionLocal
from app.events.event_bus import publish_event
from app.events.event_types import EventType
from app.intelligence.global_graph.graph_service import get_graph_update_pipeline
from app.intelligence.industry_models.industry_learning_pipeline import get_industry_learning_pipeline
from app.intelligence.recommendation_execution_engine import record_execution_result
from app.models.recommendation_execution import RecommendationExecution
from app.models.recommendation_outcome import RecommendationOutcome


def process(payload: dict[str, object]) -> dict[str, object] | None:
    execution_id = str(payload.get('execution_id', '') or '')
    if not execution_id:
        return None

    result = payload.get('result') if isinstance(payload.get('result'), dict) else None

    session = SessionLocal()
    try:
        if result is not None:
            execution = record_execution_result(execution_id, result, db=session)
            if execution is None:
                session.commit()
                return None
        else:
            execution = session.get(RecommendationExecution, execution_id)
            if execution is None:
                session.commit()
                return None

        outcome = (
            session.query(RecommendationOutcome)
            .filter(RecommendationOutcome.recommendation_id == execution.recommendation_id)
            .order_by(RecommendationOutcome.measured_at.desc(), RecommendationOutcome.id.desc())
            .first()
        )

        session.commit()
        if outcome is None:
            return None

        dispatch = {
            'campaign_id': execution.campaign_id,
            'recommendation_id': execution.recommendation_id,
            'execution_id': execution.id,
            'outcome_id': outcome.id,
            'simulation_id': outcome.simulation_id,
            'delta': outcome.delta,
            'measured_at': outcome.measured_at.isoformat(),
        }

        get_graph_update_pipeline().update_from_outcome(dispatch)
        get_industry_learning_pipeline().update_from_outcome(dispatch)

        publish_event(EventType.OUTCOME_RECORDED.value, dispatch)
        return dispatch
    finally:
        session.close()

def record_seo_flight(*args, **kwargs):
    '''
    Compatibility stub for legacy tests.

    The old SEO flight recorder was removed when the system moved
    to the knowledge graph learning spine. Tests may still
    monkeypatch this function.
    '''
    return []

