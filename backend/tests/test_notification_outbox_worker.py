from __future__ import annotations

from datetime import UTC, datetime

from app.events.emitter import emit_event
from app.events.outbox.event_outbox import EventOutbox
from app.intelligence.workers import outbox_worker
from app.models.notification import Notification
from app.models.platform_job import PlatformJob
from app.models.reporting import MonthlyReport
from app.models.user import User
from app.services.automation_webhook_service import AUTOMATION_FANOUT_JOB_TYPE
from tests.conftest import create_test_campaign


def _report_event_pair(db_session):  # noqa: ANN001
    user = db_session.query(User).filter(User.email == "org-admin@example.com").one()
    organization_id = user.tenant_id
    campaign = create_test_campaign(
        db_session,
        organization_id,
        tenant_id=organization_id,
        name="Notification worker campaign",
        domain="notification-worker.example",
    )
    report = MonthlyReport(
        tenant_id=organization_id,
        campaign_id=campaign.id,
        month_number=1,
        report_status="generated",
        summary_json="{}",
        generated_at=datetime.now(UTC),
    )
    db_session.add(report)
    db_session.flush()
    first = emit_event(
        db_session,
        tenant_id=organization_id,
        event_type="report.generated",
        payload={
            "campaign_id": campaign.id,
            "report_id": report.id,
            "revision": 1,
        },
    )
    repeat = emit_event(
        db_session,
        tenant_id=organization_id,
        event_type="report.regenerated",
        payload={
            "campaign_id": campaign.id,
            "report_id": report.id,
            "revision": 2,
        },
    )
    return first, repeat


def test_outbox_worker_materializes_once_and_reports_replay_and_cooldown(
    db_session,
) -> None:
    first, repeat = _report_event_pair(db_session)
    db_session.commit()

    result = outbox_worker.process({"limit": 20})
    db_session.expire_all()

    assert result["processed"] == 2
    assert result["failed"] == 0
    assert result["notifications_created"] == 1
    assert result["notification_outcomes"] == {
        "created": 1,
        "exact_replay": 0,
        "semantic_cooldown": 1,
        "ignored": 0,
    }
    notification = db_session.query(Notification).one()
    assert notification.source_event_id in {first.event_id, repeat.event_id}
    assert notification.event_type == "report.ready"

    sources = (
        db_session.query(EventOutbox)
        .filter(EventOutbox.id.in_([first.event_id, repeat.event_id]))
        .all()
    )
    for source in sources:
        source.status = "pending"
        source.processed_at = None
    db_session.commit()

    replayed = outbox_worker.process({"limit": 20})
    db_session.expire_all()

    assert replayed["processed"] == 2
    assert replayed["notifications_created"] == 0
    assert replayed["notification_outcomes"] == {
        "created": 0,
        "exact_replay": 1,
        "semantic_cooldown": 1,
        "ignored": 0,
    }
    assert db_session.query(Notification).count() == 1


def test_rolled_back_event_never_materializes_a_notification(db_session) -> None:
    _report_event_pair(db_session)
    db_session.rollback()

    result = outbox_worker.process({"limit": 20})

    assert result["processed"] == 0
    assert result["notifications_created"] == 0
    assert result["notification_outcomes"] == {
        "created": 0,
        "exact_replay": 0,
        "semantic_cooldown": 0,
        "ignored": 0,
    }
    assert db_session.query(Notification).count() == 0


def test_materialization_failure_marks_source_failed_without_publishing(
    db_session,
    monkeypatch,
) -> None:
    user = db_session.query(User).filter(User.email == "org-admin@example.com").one()
    event = emit_event(
        db_session,
        tenant_id=user.tenant_id,
        event_type="tenant.created",
        payload={"name": "Notification failure proof"},
    )
    db_session.commit()

    def _fail_materialization(*_args, **_kwargs):
        raise RuntimeError("notification materialization unavailable")

    monkeypatch.setattr(
        outbox_worker,
        "materialize_notification_for_outbox_event",
        _fail_materialization,
    )

    result = outbox_worker.process({"limit": 20})
    db_session.expire_all()

    assert result["processed"] == 0
    assert result["failed"] == 1
    assert result["notifications_created"] == 0
    source = db_session.get(EventOutbox, event.event_id)
    assert source is not None
    assert source.status == "failed"
    assert source.processed_at is not None
    assert db_session.query(Notification).count() == 0


def test_publish_failure_rolls_back_notification_and_fanout_before_marking_failed(
    db_session,
    monkeypatch,
) -> None:
    event, ignored_repeat = _report_event_pair(db_session)
    db_session.flush()
    repeat_source = db_session.get(EventOutbox, ignored_repeat.event_id)
    assert repeat_source is not None
    repeat_source.status = "processed"
    repeat_source.processed_at = datetime.now(UTC)
    db_session.commit()

    def _fail_publish(*_args, **_kwargs) -> None:
        raise RuntimeError("in-process event delivery unavailable")

    monkeypatch.setattr(outbox_worker.event_bus, "publish", _fail_publish)

    result = outbox_worker.process({"limit": 20})
    db_session.expire_all()

    assert result == {
        "processed": 0,
        "failed": 1,
        "automation_fanout_jobs": 0,
        "notifications_created": 0,
        "notification_outcomes": {
            "created": 0,
            "exact_replay": 0,
            "semantic_cooldown": 0,
            "ignored": 0,
        },
        "event_ids": [],
    }
    source = db_session.get(EventOutbox, event.event_id)
    assert source is not None
    assert source.status == "failed"
    assert source.processed_at is not None
    assert db_session.query(Notification).count() == 0
    assert (
        db_session.query(PlatformJob)
        .filter(
            PlatformJob.job_type == AUTOMATION_FANOUT_JOB_TYPE,
            PlatformJob.entity_id == event.event_id,
        )
        .count()
        == 0
    )
