from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import threading
import uuid

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import set_session_security_context
from app.events.emitter import EventEnvelope
from app.events.outbox.event_outbox import EventOutbox
from app.intelligence.workers import outbox_worker
from app.models.notification import Notification, NotificationUserState
from app.models.organization import Organization
from app.models.platform_job import PlatformJob
from app.models.reporting import MonthlyReport
from app.models.user import User
from app.services import notification_service
from app.services.automation_webhook_service import AUTOMATION_FANOUT_JOB_TYPE
from tests.conftest import create_test_campaign


pytestmark = pytest.mark.postgres_required


def _source_and_notification(
    *,
    organization: Organization,
    observed_at: datetime,
    event_type: str,
) -> tuple[EventOutbox, Notification]:
    source_event_id = str(uuid.uuid4())
    source_event_type = "report.generated" if event_type == "report.ready" else "execution.failed"
    envelope = EventEnvelope(
        event_id=source_event_id,
        tenant_id=organization.id,
        event_type=source_event_type,
        timestamp=observed_at.isoformat(),
        payload={"security_test": True},
    )
    source = EventOutbox(
        id=source_event_id,
        tenant_id=organization.id,
        event_type=source_event_type,
        payload_json=envelope.model_dump_json(),
        payload_hash=hashlib.sha256(source_event_id.encode("ascii")).hexdigest(),
        status="processed",
        created_at=observed_at,
        processed_at=observed_at,
    )
    notification = Notification(
        schema_version="alt1-notification-v1",
        tenant_id=organization.id,
        organization_id=organization.id,
        location_id=None,
        organization_name=organization.name,
        location_name=None,
        event_type=event_type,
        severity="information" if event_type == "report.ready" else "needs_attention",
        source_event_id=source_event_id,
        source_event_type=source_event_type,
        source_label="Saved reports" if event_type == "report.ready" else "Approved actions",
        resource_type="report" if event_type == "report.ready" else "action",
        resource_id=str(uuid.uuid4()),
        title="A report is ready" if event_type == "report.ready" else "Action needs attention",
        meaning="Saved customer-safe meaning.",
        action_label="Review report" if event_type == "report.ready" else "Review recovery guidance",
        action_url="/reports" if event_type == "report.ready" else "/opportunities",
        freshness_at=observed_at,
        observed_at=observed_at,
        semantic_fingerprint=hashlib.sha256(f"semantic:{source_event_id}".encode()).hexdigest(),
        cooldown_window_started_at=observed_at,
        cooldown_expires_at=observed_at + timedelta(hours=6),
        created_at=observed_at,
    )
    return source, notification


def _report_source_event(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    report_id: str,
    event_type: str,
    observed_at: datetime,
) -> EventEnvelope:
    event_id = str(uuid.uuid4())
    event = EventEnvelope(
        event_id=event_id,
        tenant_id=organization_id,
        event_type=event_type,
        timestamp=observed_at.isoformat(),
        payload={"campaign_id": campaign_id, "report_id": report_id},
    )
    db.add(
        EventOutbox(
            id=event_id,
            tenant_id=organization_id,
            event_type=event_type,
            payload_json=event.model_dump_json(),
            payload_hash=hashlib.sha256(event_id.encode("ascii")).hexdigest(),
            status="pending",
            created_at=observed_at,
        )
    )
    db.flush()
    return event


def test_notification_rls_isolates_tenants_and_member_state_and_parent_is_immutable(
    db_session: Session,
) -> None:
    user_a = db_session.query(User).filter(User.email == "a@example.com").one()
    user_b = db_session.query(User).filter(User.email == "b@example.com").one()
    owner_a = db_session.query(User).filter(User.email == "org-owner@example.com").one()
    org_a = db_session.get(Organization, user_a.tenant_id)
    org_b = db_session.get(Organization, user_b.tenant_id)
    assert org_a is not None
    assert org_b is not None
    org_a_id = org_a.id
    org_b_id = org_b.id
    org_a_name = org_a.name
    org_b_name = org_b.name
    db_session.commit()
    bind = db_session.get_bind()

    platform_session = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            platform_session,
            tenant_id=org_a_id,
            organization_id=org_a_id,
            user_id=owner_a.id,
            platform_access=True,
        )
        source_a, notification_a = _source_and_notification(
            organization=Organization(id=org_a_id, name=org_a_name),
            observed_at=datetime(2026, 8, 22, 19, 0, tzinfo=UTC),
            event_type="report.ready",
        )
        source_a_2, notification_a_2 = _source_and_notification(
            organization=Organization(id=org_a_id, name=org_a_name),
            observed_at=datetime(2026, 8, 22, 19, 1, tzinfo=UTC),
            event_type="action.failed",
        )
        source_b, notification_b = _source_and_notification(
            organization=Organization(id=org_b_id, name=org_b_name),
            observed_at=datetime(2026, 8, 22, 19, 2, tzinfo=UTC),
            event_type="action.failed",
        )
        platform_session.add_all([source_a, source_a_2, source_b])
        platform_session.flush()
        platform_session.add_all([notification_a, notification_a_2, notification_b])
        platform_session.commit()
        notification_a_id = notification_a.id
        notification_a_2_id = notification_a_2.id
        notification_b_id = notification_b.id
    finally:
        platform_session.close()

    tenant_a_session = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            tenant_a_session,
            tenant_id=org_a_id,
            organization_id=org_a_id,
            user_id=user_a.id,
            platform_access=False,
        )
        visible_ids = set(tenant_a_session.execute(select(Notification.id)).scalars().all())
        assert visible_ids == {notification_a_id, notification_a_2_id}
        assert tenant_a_session.get(Notification, notification_b_id) is None
        read_at = datetime.now(UTC)
        state = NotificationUserState(
            tenant_id=org_a_id,
            organization_id=org_a_id,
            notification_id=notification_a_id,
            user_id=user_a.id,
            read_at=read_at,
            dismissed_at=None,
            created_at=read_at,
            updated_at=read_at,
        )
        tenant_a_session.add(state)
        tenant_a_session.commit()
        state.dismissed_at = read_at + timedelta(seconds=1)
        state.updated_at = state.dismissed_at
        tenant_a_session.commit()
        state_id = state.id
        state_created_at = state.created_at
        state_dismissed_at = state.dismissed_at
        assert tenant_a_session.execute(select(NotificationUserState.id)).scalars().all() == [
            state.id
        ]
    finally:
        tenant_a_session.close()

    foreign_state_session = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            foreign_state_session,
            tenant_id=org_a_id,
            organization_id=org_a_id,
            user_id=user_a.id,
            platform_access=False,
        )
        changed_at = datetime.now(UTC)
        foreign_state_session.add(
            NotificationUserState(
                tenant_id=org_a_id,
                organization_id=org_a_id,
                notification_id=notification_a_id,
                user_id=owner_a.id,
                read_at=changed_at,
                dismissed_at=None,
                created_at=changed_at,
                updated_at=changed_at,
            )
        )
        with pytest.raises(DBAPIError):
            foreign_state_session.flush()
    finally:
        foreign_state_session.rollback()
        foreign_state_session.close()

    def assert_member_state_update_rejected(**values: object) -> None:
        restricted_session = Session(bind=bind, autoflush=False, autocommit=False)
        try:
            set_session_security_context(
                restricted_session,
                tenant_id=org_a_id,
                organization_id=org_a_id,
                user_id=user_a.id,
                platform_access=False,
            )
            with pytest.raises(DBAPIError):
                restricted_session.execute(
                    update(NotificationUserState)
                    .where(NotificationUserState.id == state_id)
                    .values(**values)
                )
        finally:
            restricted_session.rollback()
            restricted_session.close()

    assert_member_state_update_rejected(notification_id=notification_a_2_id)
    assert_member_state_update_rejected(
        created_at=state_created_at - timedelta(seconds=1)
    )
    assert_member_state_update_rejected(
        dismissed_at=None,
        updated_at=state_dismissed_at + timedelta(seconds=1),
    )
    assert_member_state_update_rejected(
        read_at=read_at - timedelta(seconds=1),
        updated_at=state_dismissed_at + timedelta(seconds=1),
    )

    verification_session = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        persisted_state = verification_session.get(NotificationUserState, state_id)
        assert persisted_state is not None
        assert persisted_state.notification_id == notification_a_id
        assert persisted_state.created_at == state_created_at
        assert persisted_state.read_at == read_at
        assert persisted_state.dismissed_at == state_dismissed_at
    finally:
        verification_session.close()

    tenant_b_session = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            tenant_b_session,
            tenant_id=org_b_id,
            organization_id=org_b_id,
            user_id=user_b.id,
            platform_access=False,
        )
        visible_ids = set(tenant_b_session.execute(select(Notification.id)).scalars().all())
        assert visible_ids == {notification_b_id}
        assert tenant_b_session.execute(select(NotificationUserState.id)).scalars().all() == []
    finally:
        tenant_b_session.close()

    immutable_session = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        with pytest.raises(DBAPIError):
            immutable_session.execute(
                update(Notification)
                .where(Notification.id == notification_a_id)
                .values(meaning="The durable source truth must not change.")
            )
    finally:
        immutable_session.rollback()
        immutable_session.close()


def test_postgres_semantic_cooldown_serializes_same_fingerprint(
    apply_migrations,
    db_session: Session,
    monkeypatch,
) -> None:
    db_session.query(EventOutbox).filter(EventOutbox.status == "pending").update(
        {EventOutbox.status: "processed"},
        synchronize_session=False,
    )
    user = db_session.query(User).filter(User.email == "org-admin@example.com").one()
    organization_id = user.tenant_id
    campaign = create_test_campaign(
        db_session,
        organization_id,
        tenant_id=organization_id,
        name="Concurrent notification report",
        domain="notification-concurrency.example",
    )
    observed_at = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    report = MonthlyReport(
        tenant_id=organization_id,
        campaign_id=campaign.id,
        month_number=1,
        report_status="generated",
        summary_json="{}",
        generated_at=observed_at,
    )
    db_session.add(report)
    db_session.flush()
    first_event = _report_source_event(
        db_session,
        organization_id=organization_id,
        campaign_id=campaign.id,
        report_id=report.id,
        event_type="report.generated",
        observed_at=observed_at,
    )
    second_event = _report_source_event(
        db_session,
        organization_id=organization_id,
        campaign_id=campaign.id,
        report_id=report.id,
        event_type="report.regenerated",
        observed_at=observed_at + timedelta(minutes=2),
    )
    db_session.commit()

    engine = create_engine(str(apply_migrations["database_url"]), pool_pre_ping=True)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    original_lock = notification_service._lock_semantic_fingerprint
    before_lock = threading.Barrier(2)
    results: dict[str, tuple[str, str | None]] = {}
    errors: list[BaseException] = []

    def synchronized_lock(db, **kwargs) -> None:  # noqa: ANN001
        before_lock.wait(timeout=5)
        original_lock(db, **kwargs)

    monkeypatch.setattr(
        notification_service,
        "_lock_semantic_fingerprint",
        synchronized_lock,
    )

    def materialize(name: str, event: EventEnvelope) -> None:
        session = session_local()
        try:
            result = notification_service.materialize_notification_for_outbox_event(
                session,
                event=event,
            )
            notification_id = (
                result.notification.id if result.notification is not None else None
            )
            session.commit()
            results[name] = (result.outcome, notification_id)
        except BaseException as exc:  # pragma: no cover - asserted by parent thread
            session.rollback()
            errors.append(exc)
        finally:
            session.close()

    first = threading.Thread(
        target=materialize,
        args=("first", first_event),
        name="notification-semantic-first",
        daemon=True,
    )
    second = threading.Thread(
        target=materialize,
        args=("second", second_event),
        name="notification-semantic-second",
        daemon=True,
    )
    try:
        first.start()
        second.start()
        first.join(timeout=10)
        second.join(timeout=10)
    finally:
        if first.is_alive() or second.is_alive():
            before_lock.abort()
            first.join(timeout=2)
            second.join(timeout=2)
        engine.dispose()

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert sorted(outcome for outcome, _ in results.values()) == [
        "created",
        "semantic_cooldown",
    ]
    assert len({notification_id for _, notification_id in results.values()}) == 1
    db_session.expire_all()
    assert db_session.query(Notification).count() == 1


def test_postgres_outbox_workers_release_semantic_locks_per_row_without_deadlock(
    apply_migrations,
    db_session: Session,
    monkeypatch,
) -> None:
    db_session.query(EventOutbox).filter(EventOutbox.status == "pending").update(
        {EventOutbox.status: "processed"},
        synchronize_session=False,
    )
    user = db_session.query(User).filter(User.email == "org-admin@example.com").one()
    organization_id = user.tenant_id
    campaign_a = create_test_campaign(
        db_session,
        organization_id,
        tenant_id=organization_id,
        name="Crossed notification A",
        domain="notification-cross-a.example",
    )
    campaign_b = create_test_campaign(
        db_session,
        organization_id,
        tenant_id=organization_id,
        name="Crossed notification B",
        domain="notification-cross-b.example",
    )
    observed_at = datetime(2026, 8, 22, 21, 0, tzinfo=UTC)
    report_a = MonthlyReport(
        tenant_id=organization_id,
        campaign_id=campaign_a.id,
        month_number=1,
        report_status="generated",
        summary_json="{}",
        generated_at=observed_at,
    )
    report_b = MonthlyReport(
        tenant_id=organization_id,
        campaign_id=campaign_b.id,
        month_number=1,
        report_status="generated",
        summary_json="{}",
        generated_at=observed_at,
    )
    db_session.add_all([report_a, report_b])
    db_session.flush()
    event_a_1 = _report_source_event(
        db_session,
        organization_id=organization_id,
        campaign_id=campaign_a.id,
        report_id=report_a.id,
        event_type="report.generated",
        observed_at=observed_at,
    )
    event_b_1 = _report_source_event(
        db_session,
        organization_id=organization_id,
        campaign_id=campaign_b.id,
        report_id=report_b.id,
        event_type="report.generated",
        observed_at=observed_at + timedelta(seconds=1),
    )
    event_b_2 = _report_source_event(
        db_session,
        organization_id=organization_id,
        campaign_id=campaign_b.id,
        report_id=report_b.id,
        event_type="report.regenerated",
        observed_at=observed_at + timedelta(seconds=2),
    )
    event_a_2 = _report_source_event(
        db_session,
        organization_id=organization_id,
        campaign_id=campaign_a.id,
        report_id=report_a.id,
        event_type="report.regenerated",
        observed_at=observed_at + timedelta(seconds=3),
    )
    source_event_ids = {
        event_a_1.event_id,
        event_b_1.event_id,
        event_b_2.event_id,
        event_a_2.event_id,
    }
    db_session.commit()

    engine = create_engine(str(apply_migrations["database_url"]), pool_pre_ping=True)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(outbox_worker, "SessionLocal", session_local)
    monkeypatch.setattr(
        outbox_worker,
        "queue_fanout_for_outbox_event",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        outbox_worker.event_bus,
        "publish",
        lambda *_args, **_kwargs: None,
    )
    original_materialize = outbox_worker.materialize_notification_for_outbox_event
    a_lock_held = threading.Event()
    b_lock_held = threading.Event()

    def synchronized_materialize(db, *, event):  # noqa: ANN001
        result = original_materialize(db, event=event)
        thread_name = threading.current_thread().name
        if (
            thread_name == "notification-worker-first"
            and event.event_id == event_a_1.event_id
        ):
            a_lock_held.set()
            if not b_lock_held.wait(timeout=5):
                raise AssertionError("Second worker never acquired the B semantic lock")
        elif (
            thread_name == "notification-worker-second"
            and event.event_id in {event_b_1.event_id, event_b_2.event_id}
        ):
            b_lock_held.set()
        return result

    monkeypatch.setattr(
        outbox_worker,
        "materialize_notification_for_outbox_event",
        synchronized_materialize,
    )
    results: dict[str, dict[str, object]] = {}
    errors: list[BaseException] = []

    def run_worker(name: str) -> None:
        try:
            results[name] = outbox_worker.process({"limit": 2})
        except BaseException as exc:  # pragma: no cover - asserted by parent thread
            errors.append(exc)

    first = threading.Thread(
        target=run_worker,
        args=("first",),
        name="notification-worker-first",
        daemon=True,
    )
    second = threading.Thread(
        target=run_worker,
        args=("second",),
        name="notification-worker-second",
        daemon=True,
    )
    try:
        first.start()
        assert a_lock_held.wait(timeout=5), "First worker never acquired the A semantic lock"
        second.start()
        first.join(timeout=12)
        second.join(timeout=12)
    finally:
        b_lock_held.set()
        first.join(timeout=2)
        if second.ident is not None:
            second.join(timeout=2)
        engine.dispose()

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert set(results) == {"first", "second"}
    assert sum(int(result["processed"]) for result in results.values()) == 4
    assert sum(int(result["failed"]) for result in results.values()) == 0
    assert sum(int(result["notifications_created"]) for result in results.values()) == 2
    assert (
        sum(
            int(result["notification_outcomes"]["semantic_cooldown"])
            for result in results.values()
        )
        == 2
    )
    db_session.expire_all()
    sources = (
        db_session.query(EventOutbox)
        .filter(EventOutbox.id.in_(source_event_ids))
        .all()
    )
    assert len(sources) == 4
    assert {source.status for source in sources} == {"processed"}
    assert db_session.query(Notification).count() == 2


def test_postgres_publish_failure_rolls_back_notification_and_fanout(
    apply_migrations,
    db_session: Session,
    monkeypatch,
) -> None:
    db_session.query(EventOutbox).filter(EventOutbox.status == "pending").update(
        {EventOutbox.status: "processed"},
        synchronize_session=False,
    )
    user = db_session.query(User).filter(User.email == "org-admin@example.com").one()
    organization_id = user.tenant_id
    campaign = create_test_campaign(
        db_session,
        organization_id,
        tenant_id=organization_id,
        name="Atomic notification failure",
        domain="notification-atomicity.example",
    )
    observed_at = datetime(2026, 8, 22, 22, 0, tzinfo=UTC)
    report = MonthlyReport(
        tenant_id=organization_id,
        campaign_id=campaign.id,
        month_number=1,
        report_status="generated",
        summary_json="{}",
        generated_at=observed_at,
    )
    db_session.add(report)
    db_session.flush()
    event = _report_source_event(
        db_session,
        organization_id=organization_id,
        campaign_id=campaign.id,
        report_id=report.id,
        event_type="report.generated",
        observed_at=observed_at,
    )
    db_session.commit()

    engine = create_engine(str(apply_migrations["database_url"]), pool_pre_ping=True)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(outbox_worker, "SessionLocal", session_local)

    def fail_publish(*_args, **_kwargs) -> None:
        raise RuntimeError("in-process event delivery unavailable")

    monkeypatch.setattr(outbox_worker.event_bus, "publish", fail_publish)
    try:
        result = outbox_worker.process({"limit": 1})
    finally:
        engine.dispose()

    assert result["processed"] == 0
    assert result["failed"] == 1
    assert result["automation_fanout_jobs"] == 0
    assert result["notifications_created"] == 0
    db_session.expire_all()
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
