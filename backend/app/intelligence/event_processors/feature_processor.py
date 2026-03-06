from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.events.event_bus import publish_event
from app.events.event_types import EventType
from app.intelligence.feature_store import compute_features


def process(payload: dict[str, object]) -> dict[str, object] | None:
    campaign_id = str(payload.get('campaign_id', '') or '')
    if not campaign_id:
        return None

    db = payload.get('db')
    if isinstance(db, Session):
        features = compute_features(campaign_id, db=db, persist=True, publish=False)
        publish_event(EventType.FEATURE_UPDATED.value, {'campaign_id': campaign_id, 'features': features})
        return {'campaign_id': campaign_id, 'features': features}

    session = SessionLocal()
    try:
        features = compute_features(campaign_id, db=session, persist=True, publish=False)
        session.commit()
        publish_event(EventType.FEATURE_UPDATED.value, {'campaign_id': campaign_id, 'features': features})
        return {'campaign_id': campaign_id, 'features': features}
    finally:
        session.close()
