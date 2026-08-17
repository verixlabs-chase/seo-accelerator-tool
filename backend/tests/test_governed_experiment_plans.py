import json

import pytest
from fastapi import HTTPException

from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.experiment import ExperimentAssignment
from app.models.governed_experiment import GovernedExperimentPlan
from app.models.tenant import Tenant
from app.models.user import User
from app.services import governed_experiment_plan_service


def _learning_group(*, included_count: int, review_ready: bool) -> dict:
    return {
        "summary": {"latest_measured_at": None},
        "groups": [
            {
                "action_id": "technical.reduce_render_blocking",
                "action_label": "Improve page loading speed",
                "measurement_track": "website",
                "metric_id": "cwv.lcp",
                "metric_label": "Largest Contentful Paint",
                "direction": "lower_is_better",
                "measurement_contract_version": "2.0",
                "sample_count": max(1, included_count),
                "included_count": included_count,
                "pending_review_count": 0,
                "excluded_count": 0,
                "review_ready": review_ready,
                "examples_needed": max(0, 5 - included_count),
            }
        ],
        "observations": [],
    }


def _create_campaign(db_session):
    tenant = db_session.query(Tenant).filter(Tenant.name == "Tenant A").one()
    user = db_session.query(User).filter(User.email == "a@example.com").one()
    campaign = Campaign(
        tenant_id=tenant.id,
        organization_id=tenant.id,
        name="Governed Test Campaign",
        domain="governed-tests.example",
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)
    return tenant, user, campaign


def _create(db_session, *, tenant, user, campaign):
    return governed_experiment_plan_service.create_plan(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        actor_user_id=user.id,
        action_id="technical.reduce_render_blocking",
        metric_id="cwv.lcp",
        measurement_contract_version="2.0",
        hypothesis=(
            "A limited loading-speed improvement will lower the saved page-loading "
            "measurement without harming protected measurements."
        ),
        design_type="staggered_rollout",
        minimum_sample_size=10,
        observation_window_days=28,
        guardrail_metric_ids=["search.visits", "search.visits", "cwv.lcp"],
        rollback_steps=["Restore the approved starting version."],
    )


def test_draft_is_idempotent_and_cannot_be_approved_before_review_threshold(
    db_session,
    monkeypatch,
):
    tenant, user, campaign = _create_campaign(db_session)
    monkeypatch.setattr(
        governed_experiment_plan_service.outcome_learning_service,
        "get_campaign_outcome_learning",
        lambda *args, **kwargs: _learning_group(
            included_count=4,
            review_ready=False,
        ),
    )

    first = _create(db_session, tenant=tenant, user=user, campaign=campaign)
    repeated = _create(db_session, tenant=tenant, user=user, campaign=campaign)

    assert first["created"] is True
    assert repeated["created"] is False
    assert repeated["plan"]["id"] == first["plan"]["id"]
    assert first["plan"]["status"] == "draft"
    assert first["plan"]["eligibility"]["eligible"] is False
    assert first["plan"]["eligibility"]["examples_needed"] == 1
    assert first["plan"]["guardrail_metric_ids"] == ["search.visits"]
    assert first["plan"]["safety"] == {
        "approval_is_launch": False,
        "launch_enabled": False,
        "assignments_created": False,
        "publishing_enabled": False,
        "automatic_policy_changes_enabled": False,
        "legacy_experiment_connected": False,
    }
    assert db_session.query(GovernedExperimentPlan).count() == 1

    with pytest.raises(HTTPException) as blocked:
        governed_experiment_plan_service.review_plan(
            db_session,
            tenant_id=tenant.id,
            organization_id=tenant.id,
            campaign_id=campaign.id,
            plan_id=first["plan"]["id"],
            actor_user_id=user.id,
            decision="approved",
            note=None,
        )
    assert blocked.value.status_code == 409
    assert "Review 1 more matching result" in blocked.value.detail


def test_owner_can_approve_design_without_launching_or_creating_assignments(
    db_session,
    monkeypatch,
):
    tenant, user, campaign = _create_campaign(db_session)
    monkeypatch.setattr(
        governed_experiment_plan_service.outcome_learning_service,
        "get_campaign_outcome_learning",
        lambda *args, **kwargs: _learning_group(
            included_count=5,
            review_ready=True,
        ),
    )
    created = _create(db_session, tenant=tenant, user=user, campaign=campaign)
    assignments_before = db_session.query(ExperimentAssignment).count()

    reviewed = governed_experiment_plan_service.review_plan(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        plan_id=created["plan"]["id"],
        actor_user_id=user.id,
        decision="approved",
        note="The design and stop rules were checked.",
    )

    assert reviewed["updated"] is True
    assert reviewed["plan"]["status"] == "approved"
    assert reviewed["plan"]["eligibility"]["eligible"] is True
    assert reviewed["plan"]["safety"]["approval_is_launch"] is False
    assert reviewed["plan"]["safety"]["launch_enabled"] is False
    assert reviewed["plan"]["safety"]["assignments_created"] is False
    assert db_session.query(ExperimentAssignment).count() == assignments_before

    audits = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type.in_(
                [
                    "intelligence.governed_experiment_plan_created",
                    "intelligence.governed_experiment_plan_reviewed",
                ]
            )
        )
        .all()
    )
    assert len(audits) == 2
    audit_payloads = [json.loads(item.payload_json) for item in audits]
    assert all("hypothesis" not in item for item in audit_payloads)
    assert all("review_note" not in item for item in audit_payloads)
    assert all(item["launch_enabled"] is False for item in audit_payloads)


def test_plans_are_tenant_and_organization_scoped(db_session, monkeypatch):
    tenant, user, campaign = _create_campaign(db_session)
    monkeypatch.setattr(
        governed_experiment_plan_service.outcome_learning_service,
        "get_campaign_outcome_learning",
        lambda *args, **kwargs: _learning_group(
            included_count=5,
            review_ready=True,
        ),
    )
    _create(db_session, tenant=tenant, user=user, campaign=campaign)
    other = db_session.query(Tenant).filter(Tenant.name == "Tenant B").one()

    with pytest.raises(HTTPException) as hidden:
        governed_experiment_plan_service.list_plans(
            db_session,
            tenant_id=other.id,
            organization_id=other.id,
            campaign_id=campaign.id,
        )
    assert hidden.value.status_code == 404


def test_controlled_test_api_is_empty_safe_and_tenant_scoped(client, db_session):
    _tenant, _user, campaign = _create_campaign(db_session)
    login_a = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "pass-a"},
    )
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": "b@example.com", "password": "pass-b"},
    )
    assert login_a.status_code == 200
    assert login_b.status_code == 200
    headers_a = {
        "Authorization": f"Bearer {login_a.json()['data']['access_token']}"
    }
    headers_b = {
        "Authorization": f"Bearer {login_b.json()['data']['access_token']}"
    }

    response = client.get(
        f"/api/v1/intelligence/controlled-tests?campaign_id={campaign.id}",
        headers=headers_a,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["items"] == []
    assert data["count"] == 0
    assert data["safety"]["launch_enabled"] is False
    assert data["safety"]["assignments_created"] is False
    assert data["truth"]["provider_state"] == "saved_governed_designs"

    missing_evidence = client.post(
        f"/api/v1/intelligence/controlled-tests?campaign_id={campaign.id}",
        headers=headers_a,
        json={
            "action_id": "technical.reduce_render_blocking",
            "metric_id": "cwv.lcp",
            "measurement_contract_version": "2.0",
            "hypothesis": "A limited speed improvement will improve page loading.",
            "design_type": "staggered_rollout",
            "minimum_sample_size": 10,
            "observation_window_days": 28,
            "guardrail_metric_ids": [],
            "rollback_steps": ["Restore the approved starting version."],
        },
    )
    assert missing_evidence.status_code == 409

    hidden = client.get(
        f"/api/v1/intelligence/controlled-tests?campaign_id={campaign.id}",
        headers=headers_b,
    )
    assert hidden.status_code == 404
