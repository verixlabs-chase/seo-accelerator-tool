import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.correlation import get_correlation_id
from app.events.outbox.event_outbox import EventOutbox
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

    payload_hash = _payload_hash(tenant_id=tenant_id, payload=payload_with_correlation)
    existing = (
        db.query(EventOutbox)
        .filter(
            EventOutbox.event_type == event_type,
            EventOutbox.payload_hash == payload_hash,
        )
        .first()
    )
    if existing is not None:
        return EventEnvelope.model_validate_json(existing.payload_json)

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
    db.add(
        EventOutbox(
            id=event.event_id,
            event_type=event.event_type,
            payload_json=event.model_dump_json(),
            payload_hash=payload_hash,
            status='pending',
            created_at=datetime.now(UTC),
        )
    )
    return event


def outbox_event_write(db: Session, tenant_id: str, event_type: str, payload: dict[str, Any]) -> EventEnvelope:
    return emit_event(db, tenant_id=tenant_id, event_type=event_type, payload=payload)


def _payload_hash(*, tenant_id: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps({'tenant_id': tenant_id, 'payload': payload}, sort_keys=True, default=str, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
