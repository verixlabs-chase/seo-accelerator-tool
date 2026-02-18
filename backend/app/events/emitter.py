import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class EventEnvelope(BaseModel):
    event_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    timestamp: str = Field(min_length=1)
    payload: dict[str, Any]


def emit_event(db: Session, tenant_id: str, event_type: str, payload: dict[str, Any]) -> EventEnvelope:
    event = EventEnvelope(
        event_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        event_type=event_type,
        timestamp=datetime.now(UTC).isoformat(),
        payload=payload,
    )
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            event_type=event.event_type,
            payload_json=event.model_dump_json(),
            created_at=datetime.now(UTC),
        )
    )
    return event
