from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.db.session import SessionLocal
from app.events.emitter import EventEnvelope
from app.events.event_bus import event_bus
from app.events.outbox.event_outbox import EventOutbox
from app.services.automation_webhook_service import queue_fanout_for_outbox_event
from app.services.notification_service import materialize_notification_for_outbox_event


NotificationOutcome = Literal[
    "created",
    "exact_replay",
    "semantic_cooldown",
    "ignored",
]


@dataclass(frozen=True)
class _RowProcessingResult:
    processed: bool
    event_id: str | None = None
    automation_fanout_job_created: bool = False
    notification_outcome: NotificationOutcome | None = None


def process(payload: dict[str, object] | None = None) -> dict[str, object]:
    limit = max(0, int((payload or {}).get("limit", 100) or 100))
    processed = 0
    failed = 0
    automation_fanout_jobs = 0
    notification_outcomes = {
        "created": 0,
        "exact_replay": 0,
        "semantic_cooldown": 0,
        "ignored": 0,
    }
    published_event_ids: list[str] = []

    for _ in range(limit):
        result = _process_next_pending_event()
        if result is None:
            break
        if not result.processed:
            failed += 1
            continue

        processed += 1
        if result.event_id is not None:
            published_event_ids.append(result.event_id)
        if result.automation_fanout_job_created:
            automation_fanout_jobs += 1
        if result.notification_outcome is not None:
            notification_outcomes[result.notification_outcome] += 1

    return {
        "processed": processed,
        "failed": failed,
        "automation_fanout_jobs": automation_fanout_jobs,
        "notifications_created": notification_outcomes["created"],
        "notification_outcomes": notification_outcomes,
        "event_ids": published_event_ids,
    }


def _process_next_pending_event() -> _RowProcessingResult | None:
    """Lock and finish one outbox row without holding locks across the batch."""
    session = SessionLocal()
    try:
        with session.begin():
            row = (
                session.query(EventOutbox)
                .filter(EventOutbox.status == "pending")
                .order_by(EventOutbox.created_at.asc(), EventOutbox.id.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
                .one_or_none()
            )
            if row is None:
                return None

            try:
                # Keep the row lock in the outer transaction. If any processing
                # step fails, the savepoint removes all database side effects
                # before that same clean transaction records the failure.
                with session.begin_nested():
                    event = EventEnvelope.model_validate_json(row.payload_json)
                    _process_learning_event(session, event=event)
                    notification_result = materialize_notification_for_outbox_event(
                        session,
                        event=event,
                    )
                    fanout_created = queue_fanout_for_outbox_event(
                        session,
                        event=event,
                    )
                    event_bus.publish(
                        event.event_type,
                        event.model_dump(mode="python"),
                    )
            except Exception:  # noqa: BLE001
                row.status = "failed"
                row.processed_at = datetime.now(UTC)
                return _RowProcessingResult(processed=False)

            row.status = "processed"
            row.processed_at = datetime.now(UTC)
            return _RowProcessingResult(
                processed=True,
                event_id=row.id,
                automation_fanout_job_created=fanout_created,
                notification_outcome=notification_result.outcome,
            )
    finally:
        session.close()


def _process_learning_event(session, *, event: EventEnvelope) -> None:
    _ = session
    _ = event
    return None
