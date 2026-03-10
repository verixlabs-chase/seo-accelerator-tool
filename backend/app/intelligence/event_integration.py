from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session


def process_learning_event(db: Session, *, tenant_id: str, event_type: str, payload: dict[str, Any]) -> None:
    _ = db
    _ = tenant_id
    _ = event_type
    _ = payload
    return None
