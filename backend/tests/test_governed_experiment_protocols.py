import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.experiment import ExperimentAssignment
from app.models.governed_experiment import (
    GovernedExperimentGuardrailCheck,
    GovernedExperimentPlan,
    GovernedExperimentProtocol,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.services import governed_experiment_protocol_service


def _create_campaign(db_session):
    tenant = db_session.query(Tenant).filter(Tenant.name == "Tenant A").one()
    user = db_session.query(User).filter(User.email == "a@example.com").one()
    campaign = Campaign(
        tenant_id=tenant.id,
        organization_id=tenant.id,
        name="Protocol Test Campaign",
        domain="protocol-tests.example",
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)
    return tenant, user, campaign


def _plan(db_session, *, tenant, user, campaign, status="approved"):
    row = GovernedExperimentPlan(
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        action_id="technical.reduce_render_blocking",
        metric_id="cwv.lcp",
        measurement_contract_version="2.0",
        hypothesis="A limited speed change will improve the saved page-load result.",
        design_type="staggered_rollout",
        status=status,
        minimum_sample_size=10,
        observation_window_days=14,
        guardrail_metric_ids=["organic.impressions"],
        eligibility_snapshot={"eligible": True},
        stop_rules=[
            {"code": "safety_issue", "label": "Stop on a safety issue", "required": True},
            {
                "code": "primary_metric_regression",
                "label": "Stop if the main result gets worse",
                "required": True,
            },
            {"code": "data_quality_loss", "label": "Stop if data breaks", "required": True},
            {
                "code": "allowance_exhausted",
                "label": "Stop if credits run out",
                "required": True,
            },
        ],
        rollback_steps=["Restore the approved starting page version."],
        design_version="1.0",
        artifact_hash="a" * 64,
        idempotency_key="b" * 64,
        created_by_user_id=user.id,
        reviewed_by_user_id=user.id if status == "approved" else None,
        reviewed_at=datetime.now(UTC) if status == "approved" else None,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _metric(metric_id: str, *, value: float, measured_at: datetime) -> dict:
    return {
        "metric_id": metric_id,
        "display_name": "Page loading" if metric_id == "cwv.lcp" else "Times shown",
        "status": "available",
        "value": value,
        "direction": "lower_is_better" if metric_id == "cwv.lcp" else "higher_is_better",
        "source_provider": "saved_test_source",
        "source": "Saved test measurements",
        "source_record_id": f"{metric_id}:{measured_at.isoformat()}",
        "measured_at": measured_at.isoformat(),
        "entity_scope": {"campaign_id": "same-scope"},
        "scope_key": "same-scope",
        "measurement_window_days": 14,
        "insufficient_reason": None,
    }


def _stub_dependencies(monkeypatch, *, values, measured_at):
    def capture(*args, metric_id, **kwargs):
        return _metric(metric_id, value=values[metric_id], measured_at=measured_at[0])

    monkeypatch.setattr(
        governed_experiment_protocol_service.action_plan_measurement_service,
        "capture_governed_metric_snapshot",
        capture,
    )
    monkeypatch.setattr(
        governed_experiment_protocol_service.cost_economics_service,
        "get_customer_credit_summary",
        lambda *args, **kwargs: {
            "credits": {"blocked": False, "remaining": 100, "warning_level": "healthy"}
        },
    )


def _prepare_and_authorize(db_session, monkeypatch, *, tenant, user, campaign, plan, at):
    values = {"cwv.lcp": 2000.0, "organic.impressions": 100.0}
    measured_at = [at]
    _stub_dependencies(monkeypatch, values=values, measured_at=measured_at)
    prepared = governed_experiment_protocol_service.prepare_protocol(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        plan_id=plan.id,
        actor_user_id=user.id,
        now=at,
    )
    authorized = governed_experiment_protocol_service.authorize_protocol(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        protocol_id=prepared["protocol"]["id"],
        actor_user_id=user.id,
        acknowledgements={
            "reviewed_frozen_plan": True,
            "rollback_ready": True,
            "understands_no_change_is_made": True,
        },
        note="Safety steps checked.",
        now=at + timedelta(minutes=1),
    )
    return authorized["protocol"], values, measured_at


def test_protocol_requires_approved_design_and_never_creates_assignments(
    db_session, monkeypatch
):
    tenant, user, campaign = _create_campaign(db_session)
    draft = _plan(db_session, tenant=tenant, user=user, campaign=campaign, status="draft")
    before = db_session.query(ExperimentAssignment).count()

    with pytest.raises(HTTPException) as blocked:
        governed_experiment_protocol_service.prepare_protocol(
            db_session,
            tenant_id=tenant.id,
            organization_id=tenant.id,
            campaign_id=campaign.id,
            plan_id=draft.id,
            actor_user_id=user.id,
        )
    assert blocked.value.status_code == 409
    assert db_session.query(GovernedExperimentProtocol).count() == 0
    assert db_session.query(ExperimentAssignment).count() == before

    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    draft.status = "approved"
    draft.reviewed_by_user_id = user.id
    draft.reviewed_at = now
    db_session.commit()
    _stub_dependencies(
        monkeypatch,
        values={"cwv.lcp": 2000.0, "organic.impressions": 100.0},
        measured_at=[now],
    )
    prepared = governed_experiment_protocol_service.prepare_protocol(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        plan_id=draft.id,
        actor_user_id=user.id,
        now=now,
    )
    assert prepared["protocol"]["allowance_baseline"]["remaining"] == 100
    with pytest.raises(HTTPException) as missing_ack:
        governed_experiment_protocol_service.authorize_protocol(
            db_session,
            tenant_id=tenant.id,
            organization_id=tenant.id,
            campaign_id=campaign.id,
            protocol_id=prepared["protocol"]["id"],
            actor_user_id=user.id,
            acknowledgements={"reviewed_frozen_plan": True},
            note=None,
            now=now,
        )
    assert missing_ack.value.status_code == 422


def test_second_authorization_monitoring_stop_and_verified_rollback_are_audited(
    db_session, monkeypatch
):
    tenant, user, campaign = _create_campaign(db_session)
    plan = _plan(db_session, tenant=tenant, user=user, campaign=campaign)
    started = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    protocol, values, measured_at = _prepare_and_authorize(
        db_session,
        monkeypatch,
        tenant=tenant,
        user=user,
        campaign=campaign,
        plan=plan,
        at=started,
    )
    assert protocol["status"] == "authorized"
    assert protocol["safety"]["change_applied_by_protocol"] is False

    monitoring = governed_experiment_protocol_service.start_monitoring(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        protocol_id=protocol["id"],
        actor_user_id=user.id,
        evidence_references=["Approved change record #42"],
        change_applied_at=started + timedelta(minutes=2),
        now=started + timedelta(minutes=3),
    )["protocol"]
    assert monitoring["status"] == "monitoring"

    values["cwv.lcp"] = 2400.0
    measured_at[0] = started + timedelta(days=2)
    checked = governed_experiment_protocol_service.check_guardrails(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        protocol_id=protocol["id"],
        actor_user_id=user.id,
        now=started + timedelta(days=2),
    )
    assert checked["check"]["status"] == "stop_required"
    assert checked["protocol"]["status"] == "stop_required"
    assert checked["check"]["triggered_rules"][0]["code"] == "primary_metric_regression"

    with pytest.raises(HTTPException) as cannot_clear_stop:
        governed_experiment_protocol_service.check_guardrails(
            db_session,
            tenant_id=tenant.id,
            organization_id=tenant.id,
            campaign_id=campaign.id,
            protocol_id=protocol["id"],
            actor_user_id=user.id,
            now=started + timedelta(days=2, minutes=1),
        )
    assert cannot_clear_stop.value.status_code == 409
    with pytest.raises(HTTPException) as cannot_skip_undo_state:
        governed_experiment_protocol_service.verify_rollback(
            db_session,
            tenant_id=tenant.id,
            organization_id=tenant.id,
            campaign_id=campaign.id,
            protocol_id=protocol["id"],
            actor_user_id=user.id,
            rollback_steps_confirmed=True,
            evidence_references=["Restored page revision 41"],
        )
    assert cannot_skip_undo_state.value.status_code == 409

    stopped = governed_experiment_protocol_service.stop_protocol(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        protocol_id=protocol["id"],
        actor_user_id=user.id,
        reason_code="primary_metric_regression",
        note="Owner reviewed the saved decline.",
        now=started + timedelta(days=2, minutes=5),
    )["protocol"]
    assert stopped["status"] == "rollback_pending"

    verified = governed_experiment_protocol_service.verify_rollback(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        protocol_id=protocol["id"],
        actor_user_id=user.id,
        rollback_steps_confirmed=True,
        evidence_references=["Restored page revision 41"],
        now=started + timedelta(days=2, minutes=10),
    )["protocol"]
    assert verified["status"] == "rollback_verified"
    assert verified["safety"]["automatic_rollback"] is False
    assert db_session.query(GovernedExperimentGuardrailCheck).count() == 1
    assert db_session.query(ExperimentAssignment).count() == 0

    audits = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type.like("intelligence.governed_experiment_%"))
        .all()
    )
    payloads = [json.loads(item.payload_json) for item in audits]
    assert len(payloads) >= 6
    assert all(item["assignments_created"] is False for item in payloads)
    assert all(item["publishing_enabled"] is False for item in payloads)
    assert all("stop_note" not in item for item in payloads)


def test_guardrail_waits_for_new_data_then_completes_after_observation_window(
    db_session, monkeypatch
):
    tenant, user, campaign = _create_campaign(db_session)
    plan = _plan(db_session, tenant=tenant, user=user, campaign=campaign)
    started = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    protocol, _values, measured_at = _prepare_and_authorize(
        db_session,
        monkeypatch,
        tenant=tenant,
        user=user,
        campaign=campaign,
        plan=plan,
        at=started,
    )
    governed_experiment_protocol_service.start_monitoring(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        protocol_id=protocol["id"],
        actor_user_id=user.id,
        evidence_references=["Approved change record #42"],
        change_applied_at=started + timedelta(minutes=2),
        now=started + timedelta(minutes=3),
    )
    waiting = governed_experiment_protocol_service.check_guardrails(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        protocol_id=protocol["id"],
        actor_user_id=user.id,
        now=started + timedelta(days=1),
    )
    assert waiting["check"]["status"] == "waiting_for_fresh_data"
    assert waiting["protocol"]["status"] == "monitoring"

    measured_at[0] = started + timedelta(days=15)
    completed = governed_experiment_protocol_service.check_guardrails(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        protocol_id=protocol["id"],
        actor_user_id=user.id,
        now=started + timedelta(days=15),
    )
    assert completed["check"]["status"] == "completed"
    assert completed["protocol"]["status"] == "completed"


def test_protocol_list_api_is_empty_safe_and_tenant_scoped(client, db_session):
    _tenant, _user, campaign = _create_campaign(db_session)
    login_a = client.post(
        "/api/v1/auth/login", json={"email": "a@example.com", "password": "pass-a"}
    )
    login_b = client.post(
        "/api/v1/auth/login", json={"email": "b@example.com", "password": "pass-b"}
    )
    headers_a = {"Authorization": f"Bearer {login_a.json()['data']['access_token']}"}
    headers_b = {"Authorization": f"Bearer {login_b.json()['data']['access_token']}"}

    response = client.get(
        f"/api/v1/intelligence/controlled-test-protocols?campaign_id={campaign.id}",
        headers=headers_a,
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["items"] == []
    assert payload["safety"]["monitoring_only"] is True
    assert payload["safety"]["publishing_enabled"] is False
    assert payload["truth"]["provider_state"] == "saved_metric_guardrails"

    hidden = client.get(
        f"/api/v1/intelligence/controlled-test-protocols?campaign_id={campaign.id}",
        headers=headers_b,
    )
    assert hidden.status_code == 404
