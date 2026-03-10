from __future__ import annotations

from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.events.emitter import EventEnvelope
from app.events.event_bus import event_bus
from app.events.outbox.event_outbox import EventOutbox


def process(payload: dict[str, object] | None = None) -> dict[str, object]:
    session = SessionLocal()
    try:
        limit = int((payload or {}).get('limit', 100) or 100)
        rows = (
            session.query(EventOutbox)
            .filter(EventOutbox.status == 'pending')
            .order_by(EventOutbox.created_at.asc(), EventOutbox.id.asc())
            .limit(limit)
            .all()
        )
        processed = 0
        failed = 0
        published_event_ids: list[str] = []
        for row in rows:
            try:
                event = EventEnvelope.model_validate_json(row.payload_json)
                _process_learning_event(session, event=event)
                event_bus.publish(event.event_type, event.model_dump(mode='python'))
                row.status = 'processed'
                row.processed_at = datetime.now(UTC)
                processed += 1
                published_event_ids.append(row.id)
            except Exception as exc:  # noqa: BLE001
                row.status = 'failed'
                row.processed_at = datetime.now(UTC)
                failed += 1
                row.payload_json = row.payload_json
                _ = exc
        session.commit()
        return {
            'processed': processed,
            'failed': failed,
            'event_ids': published_event_ids,
        }
    finally:
        session.close()


def _process_learning_event(session, *, event: EventEnvelope) -> None:
    try:
        from app.intelligence.event_integration import process_learning_event

        process_learning_event(
            session,
            tenant_id=event.tenant_id,
            event_type=event.event_type,
            payload=dict(event.payload),
        )
    except Exception:
        return
