from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import uuid

from app.events.emitter import EventEnvelope
from app.events.outbox.event_outbox import EventOutbox
from app.intelligence.workers import outbox_worker
from app.models.business_location import BusinessLocation
from app.models.intelligence import StrategyRecommendation
from app.models.notification import Notification
from app.models.recommendation_execution import RecommendationExecution
from app.models.reporting import MonthlyReport
from app.models.user import User
from app.services.notification_service import (
    SEMANTIC_COOLDOWN,
    materialize_notification_for_outbox_event,
)
from tests.conftest import create_test_campaign


def _source_event(
    db_session,
    *,
    tenant_id: str,
    event_type: str,
    payload: dict[str, object],
    observed_at: datetime,
) -> EventEnvelope:
    event_id = str(uuid.uuid4())
    event = EventEnvelope(
        event_id=event_id,
        tenant_id=tenant_id,
        event_type=event_type,
        timestamp=observed_at.isoformat(),
        payload=payload,
    )
    db_session.add(
        EventOutbox(
            id=event_id,
            tenant_id=tenant_id,
            event_type=event_type,
            payload_json=event.model_dump_json(),
            payload_hash=hashlib.sha256(event_id.encode("ascii")).hexdigest(),
            status="pending",
            created_at=observed_at,
        )
    )
    db_session.flush()
    return event


def _location_campaign(db_session, *, tenant_id: str):
    location = BusinessLocation(
        organization_id=tenant_id,
        name="Downtown",
        domain="downtown.example",
        status="active",
    )
    db_session.add(location)
    db_session.flush()
    campaign = create_test_campaign(
        db_session,
        tenant_id,
        tenant_id=tenant_id,
        name="Downtown visibility",
        domain="downtown.example",
    )
    campaign.business_location_id = location.id
    db_session.flush()
    return location, campaign


def test_materializes_all_approved_report_sources_with_customer_safe_truth(
    db_session,
) -> None:
    user = db_session.query(User).filter(User.email == "org-admin@example.com").one()
    tenant_id = user.tenant_id
    location, campaign = _location_campaign(db_session, tenant_id=tenant_id)
    base_time = datetime(2026, 8, 22, 10, 5, tzinfo=UTC)

    created: list[tuple[MonthlyReport, EventEnvelope, Notification]] = []
    for index, internal_type in enumerate(
        ("report.generated", "report.regenerated", "onboarding.baseline_generated")
    ):
        report = MonthlyReport(
            tenant_id=tenant_id,
            campaign_id=campaign.id,
            month_number=index + 1,
            report_status="generated",
            summary_json=json.dumps({"private_snapshot": f"secret-{index}"}),
            generated_at=base_time - timedelta(minutes=30),
        )
        db_session.add(report)
        db_session.flush()
        event = _source_event(
            db_session,
            tenant_id=tenant_id,
            event_type=internal_type,
            payload={
                "campaign_id": campaign.id,
                "report_id": report.id,
                "snapshot_hash": f"private-hash-{index}",
                "result_summary": {"private": "must not be copied"},
            },
            observed_at=base_time + timedelta(minutes=index),
        )
        result = materialize_notification_for_outbox_event(db_session, event=event)
        assert result.outcome == "created"
        assert result.notification is not None
        created.append((report, event, result.notification))

    assert db_session.query(Notification).count() == 3
    first_report, first_event, first = created[0]
    assert first.event_type == "report.ready"
    assert first.tenant_id == tenant_id
    assert first.organization_id == tenant_id
    assert first.location_id == location.id
    assert first.location_name == "Downtown"
    assert first.source_event_id == first_event.event_id
    assert first.source_event_type == "report.generated"
    assert first.source_label == "Saved reports"
    assert first.resource_type == "report"
    assert first.resource_id == first_report.id
    assert first.action_url == "/reports"
    assert first.freshness_at == first_report.generated_at
    assert first.cooldown_expires_at - first.cooldown_window_started_at == SEMANTIC_COOLDOWN
    public_copy = " ".join(
        [
            first.title,
            first.meaning,
            first.action_label,
            first.action_url,
            first.source_label,
        ]
    ).lower()
    assert "private" not in public_copy
    assert "secret" not in public_copy
    assert "provider" not in public_copy

    replay = materialize_notification_for_outbox_event(db_session, event=first_event)
    assert replay.outcome == "exact_replay"
    assert replay.notification is not None
    assert replay.notification.id == first.id
    assert db_session.query(Notification).count() == 3


def test_semantic_repeat_is_suppressed_for_six_hours_even_across_clock_boundaries(
    db_session,
) -> None:
    user = db_session.query(User).filter(User.email == "org-admin@example.com").one()
    tenant_id = user.tenant_id
    _location, campaign = _location_campaign(db_session, tenant_id=tenant_id)
    report = MonthlyReport(
        tenant_id=tenant_id,
        campaign_id=campaign.id,
        month_number=1,
        report_status="generated",
        summary_json="{}",
        generated_at=datetime(2026, 8, 22, 11, 30, tzinfo=UTC),
    )
    db_session.add(report)
    db_session.flush()
    first_time = datetime(2026, 8, 22, 11, 59, tzinfo=UTC)
    first_event = _source_event(
        db_session,
        tenant_id=tenant_id,
        event_type="report.generated",
        payload={"campaign_id": campaign.id, "report_id": report.id, "revision": 1},
        observed_at=first_time,
    )
    first = materialize_notification_for_outbox_event(db_session, event=first_event)
    assert first.created is True

    repeat_event = _source_event(
        db_session,
        tenant_id=tenant_id,
        event_type="report.regenerated",
        payload={"campaign_id": campaign.id, "report_id": report.id, "revision": 2},
        observed_at=first_time + timedelta(minutes=2),
    )
    repeat = materialize_notification_for_outbox_event(db_session, event=repeat_event)
    assert repeat.outcome == "semantic_cooldown"
    assert repeat.notification is not None
    assert first.notification is not None
    assert repeat.notification.id == first.notification.id
    assert db_session.query(Notification).count() == 1

    after_cooldown_event = _source_event(
        db_session,
        tenant_id=tenant_id,
        event_type="report.regenerated",
        payload={"campaign_id": campaign.id, "report_id": report.id, "revision": 3},
        observed_at=first_time + SEMANTIC_COOLDOWN,
    )
    after_cooldown = materialize_notification_for_outbox_event(
        db_session,
        event=after_cooldown_event,
    )
    assert after_cooldown.outcome == "created"
    assert db_session.query(Notification).count() == 2


def test_materializes_action_failed_and_ignores_every_other_product_event(
    db_session,
) -> None:
    user = db_session.query(User).filter(User.email == "org-admin@example.com").one()
    tenant_id = user.tenant_id
    location, campaign = _location_campaign(db_session, tenant_id=tenant_id)
    recommendation = StrategyRecommendation(
        tenant_id=tenant_id,
        campaign_id=campaign.id,
        recommendation_type="title_optimization",
        rationale="Private rationale",
        confidence=0.9,
        confidence_score=0.9,
        evidence_json='[{"private":"evidence"}]',
        risk_tier=3,
        rollback_plan_json='{"private":"rollback"}',
        idempotency_key=f"notification-{uuid.uuid4()}",
    )
    db_session.add(recommendation)
    db_session.flush()
    failed_at = datetime(2026, 8, 22, 14, 30, tzinfo=UTC)
    execution = RecommendationExecution(
        recommendation_id=recommendation.id,
        campaign_id=campaign.id,
        execution_type="approved_title_change",
        execution_payload='{"private":"mutation"}',
        idempotency_key=f"notification-execution-{uuid.uuid4()}",
        deterministic_hash="a" * 64,
        status="failed",
        last_error="private stack trace",
        result_summary='{"private":"result"}',
        executed_at=failed_at,
    )
    db_session.add(execution)
    db_session.flush()
    failed_event = _source_event(
        db_session,
        tenant_id=tenant_id,
        event_type="execution.failed",
        payload={
            "campaign_id": campaign.id,
            "execution_id": execution.id,
            "result_summary": {"private": "provider failure body"},
        },
        observed_at=failed_at,
    )
    result = materialize_notification_for_outbox_event(db_session, event=failed_event)
    assert result.outcome == "created"
    notification = result.notification
    assert notification is not None
    assert notification.event_type == "action.failed"
    assert notification.severity == "needs_attention"
    assert notification.location_id == location.id
    assert notification.source_label == "Approved actions"
    assert notification.resource_id == execution.id
    assert notification.action_url == "/opportunities"
    assert notification.action_label == "Review recovery guidance"
    assert notification.freshness_at == failed_at
    serialized = " ".join(
        [notification.title, notification.meaning, notification.action_label]
    ).lower()
    assert "private" not in serialized
    assert "stack trace" not in serialized
    assert "provider failure" not in serialized

    unsupported = _source_event(
        db_session,
        tenant_id=tenant_id,
        event_type="execution.completed",
        payload={"campaign_id": campaign.id, "execution_id": execution.id},
        observed_at=failed_at + timedelta(minutes=1),
    )
    ignored = materialize_notification_for_outbox_event(db_session, event=unsupported)
    assert ignored.outcome == "ignored"
    assert ignored.notification is None
    assert db_session.query(Notification).count() == 1


def test_outbox_worker_commits_notification_in_the_durable_event_pass(db_session) -> None:
    db_session.query(EventOutbox).update(
        {EventOutbox.status: "processed"},
        synchronize_session=False,
    )
    user = db_session.query(User).filter(User.email == "org-admin@example.com").one()
    tenant_id = user.tenant_id
    _location, campaign = _location_campaign(db_session, tenant_id=tenant_id)
    observed_at = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    report = MonthlyReport(
        tenant_id=tenant_id,
        campaign_id=campaign.id,
        month_number=1,
        report_status="generated",
        summary_json="{}",
        generated_at=observed_at,
    )
    db_session.add(report)
    db_session.flush()
    event = _source_event(
        db_session,
        tenant_id=tenant_id,
        event_type="report.generated",
        payload={"campaign_id": campaign.id, "report_id": report.id},
        observed_at=observed_at,
    )
    db_session.commit()

    outcome = outbox_worker.process({"limit": 10})
    assert outcome["processed"] == 1
    assert outcome["failed"] == 0
    assert outcome["notifications_created"] == 1
    assert outcome["notification_outcomes"] == {
        "created": 1,
        "exact_replay": 0,
        "semantic_cooldown": 0,
        "ignored": 0,
    }
    assert outcome["event_ids"] == [event.event_id]
    db_session.expire_all()
    notification = (
        db_session.query(Notification)
        .filter(Notification.source_event_id == event.event_id)
        .one()
    )
    assert notification.event_type == "report.ready"
    assert db_session.get(EventOutbox, event.event_id).status == "processed"
    assert outbox_worker.process({"limit": 10})["notifications_created"] == 0
    assert db_session.query(Notification).count() == 1
