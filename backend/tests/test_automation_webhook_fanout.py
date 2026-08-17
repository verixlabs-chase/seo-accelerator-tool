from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from app.automation import verify_signed_automation_event
from app.events.emitter import emit_event
from app.events.outbox.event_outbox import EventOutbox
from app.intelligence.workers import outbox_worker
from app.models.automation_webhook import (
    AutomationWebhookConnection,
    AutomationWebhookDelivery,
)
from app.models.intelligence import StrategyRecommendation
from app.models.platform_job import PlatformJob
from app.models.recommendation_execution import RecommendationExecution
from app.models.reporting import MonthlyReport
from app.services import automation_webhook_service as webhook_service
from app.services import durable_job_service, job_service
from tests.conftest import create_test_campaign


BACKEND_ROOT = Path(__file__).resolve().parents[1]


MASTER_KEY_B64 = base64.b64encode(b"automation-webhook-test-key-32!!").decode("ascii")


@pytest.fixture(autouse=True)
def _automation_master_key(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["organization_id"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_verified_connection(
    client,
    monkeypatch,
    *,
    event_types: list[str] | None = None,
) -> tuple[str, str, str]:
    token, organization_id = _login(
        client, "org-owner@example.com", "pass-org-owner"
    )
    created = client.post(
        "/api/v1/automation/connections",
        json={
            "name": "Automatic product events",
            "provider": "zapier",
            "destination_url": (
                "https://hooks.zapier.com/hooks/catch/123456/automatic-events/"
            ),
            "event_types": event_types or ["report.ready"],
        },
        headers=_headers(token),
    )
    assert created.status_code == 201, created.text
    payload = created.json()["data"]
    monkeypatch.setattr(webhook_service, "_post_signed_event", lambda **_kwargs: 204)
    tested = client.post(
        f"/api/v1/automation/connections/{payload['connection']['id']}/test",
        headers=_headers(token),
    )
    assert tested.status_code == 200
    return token, organization_id, payload["signing_secret"]


def _run_job(db, job: PlatformJob, *, worker_id: str) -> dict:  # noqa: ANN001
    job_service.start_job(db, job.id, worker_id=worker_id, lease_seconds=120)
    db.commit()
    return durable_job_service.execute_claimed_job(db, job_id=job.id)


def _create_report_event(db, *, organization_id: str):  # noqa: ANN001
    campaign = create_test_campaign(
        db,
        organization_id,
        tenant_id=organization_id,
        name="Automatic report campaign",
        domain="automatic-report.example",
    )
    report = MonthlyReport(
        tenant_id=organization_id,
        campaign_id=campaign.id,
        month_number=1,
        report_status="generated",
        summary_json=json.dumps(
            {"private_snapshot": "must never leave InsightOS"}, sort_keys=True
        ),
    )
    db.add(report)
    db.flush()
    event = emit_event(
        db,
        tenant_id=organization_id,
        event_type="report.generated",
        payload={
            "campaign_id": campaign.id,
            "report_id": report.id,
            "snapshot_hash": "internal-only-hash",
        },
    )
    db.commit()
    return campaign, report, event


def _fan_out_report(db, *, organization_id: str, event_id: str):  # noqa: ANN001
    fanout_job = (
        db.query(PlatformJob)
        .filter(
            PlatformJob.job_type == webhook_service.AUTOMATION_FANOUT_JOB_TYPE,
            PlatformJob.entity_id == event_id,
        )
        .one()
    )
    assert _run_job(db, fanout_job, worker_id="fanout-worker")["status"] == "completed"
    return (
        db.query(AutomationWebhookDelivery)
        .filter(
            AutomationWebhookDelivery.source_outbox_event_id == event_id,
            AutomationWebhookDelivery.delivery_kind == "product",
        )
        .one()
    )


def test_committed_report_event_fans_out_once_and_delivers_minimal_signed_payload(
    client,
    db_session,
    monkeypatch,
) -> None:
    token, organization_id, signing_secret = _create_verified_connection(
        client, monkeypatch
    )
    campaign, report, event = _create_report_event(
        db_session, organization_id=organization_id
    )

    processed = outbox_worker.process({"limit": 20})
    assert processed["automation_fanout_jobs"] == 1
    assert event.event_id in processed["event_ids"]
    assert outbox_worker.process({"limit": 20})["automation_fanout_jobs"] == 0

    delivery = _fan_out_report(
        db_session, organization_id=organization_id, event_id=event.event_id
    )
    fanout_job = (
        db_session.query(PlatformJob)
        .filter(PlatformJob.job_type == webhook_service.AUTOMATION_FANOUT_JOB_TYPE)
        .one()
    )
    assert _run_job(db_session, fanout_job, worker_id="fanout-repeat")["status"] == (
        "completed"
    )
    assert (
        db_session.query(AutomationWebhookDelivery)
        .filter(AutomationWebhookDelivery.source_outbox_event_id == event.event_id)
        .count()
        == 1
    )

    captured: dict[str, object] = {}

    def _capture(*, destination_url: str, body: bytes, headers: dict[str, str]) -> int:
        captured.update(url=destination_url, body=body, headers=headers)
        return 202

    monkeypatch.setattr(webhook_service, "_post_signed_event", _capture)
    delivery_job = db_session.get(PlatformJob, delivery.platform_job_id)
    assert delivery_job is not None
    assert _run_job(db_session, delivery_job, worker_id="delivery-worker")["status"] == (
        "completed"
    )
    verified = verify_signed_automation_event(
        body=captured["body"],
        headers=captured["headers"],
        signing_secret=signing_secret,
    )
    assert verified.event_id == f"evt_product_{event.event_id.replace('-', '')}"
    assert verified.event_type == "report.ready"
    assert verified.organization_id == organization_id
    assert verified.location_id == campaign.business_location_id
    assert verified.resource.id == report.id
    assert verified.data["report_href"] == "/reports"
    public_json = verified.model_dump_json()
    assert "private_snapshot" not in public_json
    assert "internal-only-hash" not in public_json
    assert "provider" not in public_json.lower()
    listed = client.get("/api/v1/automation/connections", headers=_headers(token))
    proof = listed.json()["data"]["items"][0]["conformance_proof"]
    assert proof["state"] == "product_event_accepted"
    assert proof["label"] == "Real product event accepted"
    assert proof["production_proven"] is True
    assert proof["evidence_at"] is not None


def test_product_delivery_retries_then_dead_letters_and_owner_recovers(
    client,
    db_session,
    monkeypatch,
) -> None:
    token, organization_id, _secret = _create_verified_connection(client, monkeypatch)
    _campaign, _report, event = _create_report_event(
        db_session, organization_id=organization_id
    )
    outbox_worker.process({"limit": 20})
    delivery = _fan_out_report(
        db_session, organization_id=organization_id, event_id=event.event_id
    )
    delivery_job = db_session.get(PlatformJob, delivery.platform_job_id)
    assert delivery_job is not None
    monkeypatch.setattr(webhook_service, "_post_signed_event", lambda **_kwargs: 503)

    for attempt in range(1, 4):
        outcome = _run_job(
            db_session,
            delivery_job,
            worker_id=f"delivery-attempt-{attempt}",
        )
        db_session.expire_all()
        current = db_session.get(AutomationWebhookDelivery, delivery.id)
        assert current is not None
        assert current.attempt_count == attempt
        if attempt < 3:
            assert outcome["status"] == "queued"
            assert current.status == "failed"
            assert current.next_attempt_at is not None
        else:
            assert outcome["status"] == "completed"
            assert current.status == "dead_letter"
            assert current.dead_lettered_at is not None

    listed = client.get("/api/v1/automation/connections", headers=_headers(token))
    connection = listed.json()["data"]["items"][0]
    assert connection["dead_letter_count"] == 1
    assert connection["recoverable_deliveries"][0]["event_id"] == delivery.event_id

    recovered = client.post(
        f"/api/v1/automation/deliveries/{delivery.id}/recover",
        headers=_headers(token),
    )
    assert recovered.status_code == 200
    recovered_delivery = recovered.json()["data"]["delivery"]
    assert recovered_delivery["event_id"] == delivery.event_id
    assert recovered_delivery["attempt_count"] == 3
    assert recovered_delivery["max_attempts"] == 6
    assert recovered_delivery["recovery_count"] == 1
    assert recovered_delivery["status"] == "pending"

    monkeypatch.setattr(webhook_service, "_post_signed_event", lambda **_kwargs: 204)
    db_session.expire_all()
    current = db_session.get(AutomationWebhookDelivery, delivery.id)
    recovery_job = db_session.get(PlatformJob, current.platform_job_id)
    assert recovery_job is not None
    assert _run_job(db_session, recovery_job, worker_id="recovery-worker")["status"] == (
        "completed"
    )
    db_session.expire_all()
    current = db_session.get(AutomationWebhookDelivery, delivery.id)
    assert current.status == "delivered"
    assert current.attempt_count == 4


def test_pause_cancels_already_queued_delivery_without_network_call(
    client,
    db_session,
    monkeypatch,
) -> None:
    token, organization_id, _secret = _create_verified_connection(client, monkeypatch)
    _campaign, _report, event = _create_report_event(
        db_session, organization_id=organization_id
    )
    outbox_worker.process({"limit": 20})
    delivery = _fan_out_report(
        db_session, organization_id=organization_id, event_id=event.event_id
    )
    connection = db_session.get(AutomationWebhookConnection, delivery.connection_id)
    assert connection is not None
    paused = client.post(
        f"/api/v1/automation/connections/{connection.id}/pause",
        headers=_headers(token),
    )
    assert paused.status_code == 200
    assert paused.json()["data"]["connection"]["status"] == "paused"

    def _must_not_call(**_kwargs) -> int:
        raise AssertionError("paused automation must not call the destination")

    monkeypatch.setattr(webhook_service, "_post_signed_event", _must_not_call)
    delivery_job = db_session.get(PlatformJob, delivery.platform_job_id)
    assert delivery_job is not None
    assert _run_job(db_session, delivery_job, worker_id="paused-worker")["status"] == (
        "completed"
    )
    db_session.expire_all()
    assert db_session.get(AutomationWebhookDelivery, delivery.id).status == "cancelled"

    resumed = client.post(
        f"/api/v1/automation/connections/{connection.id}/resume",
        headers=_headers(token),
    )
    assert resumed.status_code == 200
    assert resumed.json()["data"]["connection"]["status"] == "active"


def test_live_event_translation_covers_recommendation_and_action_results(
    db_session,
    create_test_tenant,
    create_test_org,
) -> None:
    tenant = create_test_tenant(name="Automation translation tenant")
    organization = create_test_org(
        tenant_id=tenant.id, name="Automation translation org"
    )
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant.id,
        name="Automation translation campaign",
    )
    recommendation = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type="title_improvement",
        rationale="private rationale",
        confidence=0.9,
        confidence_score=0.9,
        evidence_json='[{"private":"evidence"}]',
        rollback_plan_json='{"private":"rollback"}',
        risk_tier=3,
        idempotency_key="automation-translation-recommendation",
    )
    db_session.add(recommendation)
    db_session.flush()
    execution = RecommendationExecution(
        recommendation_id=recommendation.id,
        campaign_id=campaign.id,
        execution_type="approved_title_change",
        execution_payload='{"private":"mutation"}',
        idempotency_key="automation-translation-execution",
        deterministic_hash="a" * 64,
        status="completed",
        result_summary='{"private":"result"}',
    )
    db_session.add(execution)
    db_session.flush()

    cases = [
        (
            "recommendation.generated",
            {"campaign_id": campaign.id, "recommendation_id": recommendation.id},
            "recommendation.ready",
        ),
        (
            "execution.completed",
            {"campaign_id": campaign.id, "execution_id": execution.id},
            "action.completed",
        ),
        (
            "execution.failed",
            {"campaign_id": campaign.id, "execution_id": execution.id},
            "action.failed",
        ),
    ]
    for internal_type, payload, expected_type in cases:
        event = emit_event(
            db_session,
            tenant_id=tenant.id,
            event_type=internal_type,
            payload=payload,
        )
        db_session.flush()
        source = db_session.get(EventOutbox, event.event_id)
        translated = webhook_service._translate_product_event(
            db_session, source=source, event=event
        )
        assert translated is not None
        assert translated.event_type == expected_type
        serialized = translated.model_dump_json()
        assert "private rationale" not in serialized
        assert '"private"' not in serialized


def test_reserved_approval_event_cannot_be_subscribed_or_fanned_out(
    client,
    db_session,
) -> None:
    token, organization_id = _login(
        client, "org-owner@example.com", "pass-org-owner"
    )
    invalid = client.post(
        "/api/v1/automation/connections",
        json={
            "name": "Reserved approval event",
            "provider": "make",
            "destination_url": "https://hook.us1.make.com/reserved-event",
            "event_types": ["approval.requested"],
        },
        headers=_headers(token),
    )
    assert invalid.status_code == 422
    event = emit_event(
        db_session,
        tenant_id=organization_id,
        event_type="approval.requested",
        payload={"campaign_id": "reserved"},
    )
    db_session.commit()
    assert webhook_service.queue_fanout_for_outbox_event(db_session, event=event) is False
    assert (
        db_session.query(PlatformJob)
        .filter(PlatformJob.entity_id == event.event_id)
        .count()
        == 0
    )


def test_automation_jobs_are_cron_driven_and_registered() -> None:
    config = json.loads((BACKEND_ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert {
        "path": "/api/v1/internal/jobs/drain",
        "schedule": "0 6 * * *",
    } in config["crons"]
    assert (
        webhook_service.AUTOMATION_FANOUT_JOB_TYPE
        in durable_job_service.DEFAULT_HANDLERS
    )
    assert (
        webhook_service.AUTOMATION_DELIVERY_JOB_TYPE
        in durable_job_service.DEFAULT_HANDLERS
    )
