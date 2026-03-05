from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.feature_store import compute_features
from app.intelligence.signal_assembler import assemble_signals
from app.intelligence.temporal_ingestion import write_temporal_signals

LEARNING_TRIGGER_EVENTS = {
    'crawl.completed',
    'report.generated',
    'automation.action_executed',
}


def process_learning_event(db: Session, *, tenant_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, int] | None:
    if event_type not in LEARNING_TRIGGER_EVENTS:
        return None
    campaign_id = str(payload.get('campaign_id', '') or '')
    if not campaign_id:
        return None

    signals = assemble_signals(campaign_id, db=db)
    write_result = write_temporal_signals(
        campaign_id,
        signals,
        db=db,
        source=f'event:{event_type}',
        tenant_id=tenant_id,
    )
    compute_features(campaign_id, db=db, persist=True)
    return write_result
