from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.events.event_bus import publish_event
from app.events.event_types import EventType
from app.intelligence.global_graph.graph_service import get_graph_update_pipeline
from app.intelligence.industry_models.industry_learning_pipeline import get_industry_learning_pipeline
from app.intelligence.pattern_engine import discover_cohort_patterns, discover_patterns_for_campaign


def process(payload: dict[str, object]) -> dict[str, object] | None:
    campaign_id = str(payload.get('campaign_id', '') or '')
    if not campaign_id:
        return None

    db = payload.get('db')
    if isinstance(db, Session):
        local_patterns = discover_patterns_for_campaign(campaign_id, db, persist_features=False, publish=False)
        cohort_patterns = discover_cohort_patterns(db, campaign_id=campaign_id)
        all_patterns = [*local_patterns, *cohort_patterns]
        features = payload.get('features') if isinstance(payload.get('features'), dict) else {}

        graph_payload = {
            'campaign_id': campaign_id,
            'patterns': all_patterns,
            'features': features,
            'detected_at': datetime.now(UTC).isoformat(),
            'model_version': 'pattern_engine_v1',
        }
        get_graph_update_pipeline().update_from_pattern(graph_payload)
        get_industry_learning_pipeline().update_from_pattern(graph_payload)

        publish_event(
            EventType.PATTERN_DISCOVERED.value,
            {'campaign_id': campaign_id, 'patterns': all_patterns, 'features': features},
        )
        return {'campaign_id': campaign_id, 'patterns': all_patterns}

    session = SessionLocal()
    try:
        local_patterns = discover_patterns_for_campaign(campaign_id, session, persist_features=False, publish=False)
        cohort_patterns = discover_cohort_patterns(session, campaign_id=campaign_id)
        all_patterns = [*local_patterns, *cohort_patterns]
        features = payload.get('features') if isinstance(payload.get('features'), dict) else {}

        graph_payload = {
            'campaign_id': campaign_id,
            'patterns': all_patterns,
            'features': features,
            'detected_at': datetime.now(UTC).isoformat(),
            'model_version': 'pattern_engine_v1',
        }
        get_graph_update_pipeline().update_from_pattern(graph_payload)
        get_industry_learning_pipeline().update_from_pattern(graph_payload)

        publish_event(
            EventType.PATTERN_DISCOVERED.value,
            {'campaign_id': campaign_id, 'patterns': all_patterns, 'features': features},
        )
        return {'campaign_id': campaign_id, 'patterns': all_patterns}
    finally:
        session.close()
