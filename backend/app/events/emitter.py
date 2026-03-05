import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.correlation import get_correlation_id
from app.core.event_bus import event_bus
from app.models.audit_log import AuditLog


class EventEnvelope(BaseModel):
    event_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    timestamp: str = Field(min_length=1)
    correlation_id: str | None = None
    payload: dict[str, Any]


def emit_event(db: Session, tenant_id: str, event_type: str, payload: dict[str, Any]) -> EventEnvelope:
    correlation_id = get_correlation_id()
    payload_with_correlation = dict(payload)
    if correlation_id and 'correlation_id' not in payload_with_correlation:
        payload_with_correlation['correlation_id'] = correlation_id

    event = EventEnvelope(
        event_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        event_type=event_type,
        timestamp=datetime.now(UTC).isoformat(),
        correlation_id=correlation_id,
        payload=payload_with_correlation,
    )

    db.add(
        AuditLog(
            tenant_id=tenant_id,
            event_type=event.event_type,
            payload_json=event.model_dump_json(),
            created_at=datetime.now(UTC),
        )
    )

    _process_learning_event(db, tenant_id=tenant_id, event_type=event_type, payload=payload_with_correlation)

    # Never fail caller because a subscriber misbehaved.
    event_bus.publish(event_type, event.model_dump(mode='python'))
    return event


def _process_learning_event(db: Session, *, tenant_id: str, event_type: str, payload: dict[str, Any]) -> None:
    try:
        from app.intelligence.event_integration import process_learning_event

        process_learning_event(db, tenant_id=tenant_id, event_type=event_type, payload=payload)
    except Exception:
        return
