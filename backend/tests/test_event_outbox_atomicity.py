from __future__ import annotations

from app.events.emitter import emit_event
from app.events.event_bus import reset_subscribers, subscribe
from app.events.outbox.event_outbox import EventOutbox
from app.intelligence.workers.outbox_worker import process as process_outbox


def test_emit_event_rollback_does_not_publish_or_persist_outbox(db_session) -> None:
    handled: list[dict[str, object]] = []
    reset_subscribers()
    subscribe('tenant.created', lambda payload: handled.append(payload))

    emit_event(
        db_session,
        tenant_id='tenant-outbox-test',
        event_type='tenant.created',
        payload={'name': 'Rollback Tenant', 'status': 'Active'},
    )
    db_session.rollback()

    assert handled == []
    assert db_session.query(EventOutbox).count() == 0


def test_outbox_worker_publishes_only_committed_events(db_session) -> None:
    handled: list[dict[str, object]] = []
    reset_subscribers()
    subscribe('tenant.created', lambda payload: handled.append(payload))

    emit_event(
        db_session,
        tenant_id='tenant-outbox-test',
        event_type='tenant.created',
        payload={'name': 'Committed Tenant', 'status': 'Active'},
    )
    db_session.commit()

    pending = db_session.query(EventOutbox).filter(EventOutbox.status == 'pending').count()
    assert pending == 1

    result = process_outbox({'limit': 10})
    db_session.expire_all()

    assert result['processed'] == 1
    assert result['failed'] == 0
    row = db_session.query(EventOutbox).one()
    assert row.status == 'processed'
    assert row.processed_at is not None
    assert len(handled) == 1
    assert handled[0]['event_type'] == 'tenant.created'
    assert handled[0]['payload']['name'] == 'Committed Tenant'
