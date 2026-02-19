from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def write_audit_log(
    db: Session,
    *,
    tenant_id: str,
    actor_user_id: str | None,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            payload_json=json.dumps(payload, separators=(",", ":"), sort_keys=True),
            created_at=datetime.now(UTC),
        )
    )
