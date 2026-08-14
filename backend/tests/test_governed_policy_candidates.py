import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.api.v1.intelligence import intelligence_router
from app.models.action_plan import ActionPlanMeasurement, ActionPlanOccurrence
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.experiment import ExperimentAssignment
from app.models.governed_experiment import (
    GovernedExperimentPlan,
    GovernedExperimentProtocol,
    GovernedPolicyCandidate,
    GovernedPolicyDecision,
    GovernedPolicyReplay,
)
from app.models.intelligence import StrategyRecommendation
from app.models.outcome_learning import OutcomeLearningReview
from app.models.policy_weights import PolicyWeight
from app.models.tenant import Tenant
from app.models.user import User
from app.services import governed_policy_candidate_service


ACTION_ID = "technical.reduce_render_blocking"
METRIC_ID = "cwv.lcp"
CONTRACT_VERSION = "2.0"


def _campaign(db_session, name="Policy Candidate Campaign"):
    tenant = db_session.query(Tenant).filter(Tenant.name == "Tenant A").one()
    user = db_session.query(User).filter(User.email == "a@example.com").one()
    campaign = Campaign(
        tenant_id=tenant.id,
        organization_id=tenant.id,
        name=name,
        domain=f"{name.lower().replace(' ', '-')}.example",
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)
    return tenant, user, campaign


def _completed_protocol(db_session, *, tenant, user, campaign, minimum_sample_size=10):
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    plan = GovernedExperimentPlan(
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        action_id=ACTION_ID,
        metric_id=METRIC_ID,
        measurement_contract_version=CONTRACT_VERSION,
        hypothesis="A limited speed change will improve the saved page-load result.",
        design_type="staggered_rollout",
        status="approved",
        minimum_sample_size=minimum_sample_size,
        observation_window_days=14,
        guardrail_metric_ids=[],
        eligibility_snapshot={"eligible": True},
        stop_rules=[],
        rollback_steps=["Restore the approved starting page version."],
        design_version="1.0",
        artifact_hash="a" * 64,
        idempotency_key=f"{campaign.id}:plan"[:64],
        created_by_user_id=user.id,
        reviewed_by_user_id=user.id,
        reviewed_at=now,
    )
    db_session.add(plan)
    db_session.flush()
    protocol = GovernedExperimentProtocol(
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        plan_id=plan.id,
        status="completed",
        protocol_version="1.0",
        plan_artifact_hash=plan.artifact_hash,
        protocol_hash="b" * 64,
        baseline_snapshot={},
        protected_baselines=[],
        allowance_baseline={},
        stop_rules=[],
        rollback_steps=list(plan.rollback_steps),
        authorization_acknowledgements={},
        change_evidence=[],
        latest_check_summary={"status": "completed"},
        rollback_evidence=[],
        created_by_user_id=user.id,
        authorized_by_user_id=user.id,
        started_by_user_id=user.id,
        authorized_at=now,
        monitoring_started_at=now,
        observation_due_at=now + timedelta(days=14),
    )
    db_session.add(protocol)
    db_session.commit()
    db_session.refresh(protocol)
    return plan, protocol


def _add_outcomes(db_session, *, tenant, user, campaign, classifications):
    base = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    for index, classification in enumerate(classifications):
        measured_at = base + timedelta(days=index)
        recommendation = StrategyRecommendation(
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            recommendation_type="technical",
            rationale="Improve page loading.",
            confidence=0.8,
            confidence_score=0.8,
            evidence_json="[]",
            risk_tier=1,
            rollback_plan_json='{"steps":[]}',
            idempotency_key=f"{campaign.id}:recommendation:{index}",
        )
        db_session.add(recommendation)
        db_session.flush()
        occurrence = ActionPlanOccurrence(
            tenant_id=tenant.id,
            organization_id=tenant.id,
            campaign_id=campaign.id,
            recommendation_id=recommendation.id,
            action_id=ACTION_ID,
            cadence="monthly",
            period_key=f"2026-{index + 1:02d}",
            timezone="UTC",
            status="completed",
            lexicon_id="seo-intelligence-core",
            lexicon_version="1.0.0",
            content_hash=f"{index:064d}",
            idempotency_key=f"{campaign.id}:occurrence:{index}",
            completed_at=measured_at - timedelta(days=14),
        )
        db_session.add(occurrence)
        db_session.flush()
        improved = classification == "improved"
        outcome_value = 1800.0 if improved else 2300.0 if classification == "worse" else 2000.0
        measurement = ActionPlanMeasurement(
            tenant_id=tenant.id,
            organization_id=tenant.id,
            campaign_id=campaign.id,
            occurrence_id=occurrence.id,
            recommendation_id=recommendation.id,
            action_id=ACTION_ID,
            measurement_status="measured",
            outcome_status="helped" if improved else "did_not_help",
            result_classification=classification,
            measurement_contract={
                "version": CONTRACT_VERSION,
                "track": "website",
                "primary_metric_id": METRIC_ID,
            },
            success_metric_ids=[METRIC_ID],
            baseline_metrics=[
                {
                    "metric_id": METRIC_ID,
                    "status": "available",
                    "value": 2000.0,
                }
            ],
            baseline_evidence=[],
            implementation_scope={},
            completion_proof=[],
            outcome_metrics=[
                {
                    "metric_id": METRIC_ID,
                    "status": "available",
                    "value": outcome_value,
                    "comparison_requirements_met": True,
                    "scope_matches": True,
                }
            ],
            outcome_evidence=[],
            observation_window_days=14,
            baseline_captured_at=measured_at - timedelta(days=28),
            work_completed_at=measured_at - timedelta(days=14),
            outcome_measured_at=measured_at,
            action_plan_hash="c" * 64,
            lexicon_id="seo-intelligence-core",
            lexicon_version="1.0.0",
        )
        db_session.add(measurement)
        db_session.flush()
        db_session.add(
            OutcomeLearningReview(
                tenant_id=tenant.id,
                organization_id=tenant.id,
                campaign_id=campaign.id,
                measurement_id=measurement.id,
                decision="included",
                confounder_codes=[],
                reviewed_by_user_id=user.id,
                reviewed_at=measured_at,
            )
        )
    db_session.commit()


def test_candidate_replay_and_future_only_approval_are_frozen_and_idempotent(db_session):
    tenant, user, campaign = _campaign(db_session)
    _plan, protocol = _completed_protocol(db_session, tenant=tenant, user=user, campaign=campaign)
    _add_outcomes(
        db_session,
        tenant=tenant,
        user=user,
        campaign=campaign,
        classifications=["improved"] * 8 + ["about_the_same", "worse"],
    )
    assignments_before = db_session.query(ExperimentAssignment).count()
    weights_before = db_session.query(PolicyWeight).count()

    created = governed_policy_candidate_service.create_candidate(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        protocol_id=protocol.id,
        actor_user_id=user.id,
    )
    candidate = created["item"]
    assert created["created"] is True
    assert candidate["policy_family"] == "action_learning_eligibility"
    assert candidate["champion_rules"]["minimum_independent_results"] == 5
    assert candidate["challenger_rules"]["minimum_independent_results"] == 10
    assert candidate["automatic_activation_allowed"] is False
    assert candidate["immutable"] is True

    repeated = governed_policy_candidate_service.create_candidate(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        protocol_id=protocol.id,
        actor_user_id=user.id,
    )
    assert repeated["created"] is False
    assert repeated["item"]["id"] == candidate["id"]

    replayed = governed_policy_candidate_service.replay_candidate(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        candidate_id=candidate["id"],
        actor_user_id=user.id,
    )
    replay = replayed["item"]["latest_replay"]
    assert replayed["created"] is True
    assert replay["status"] == "passed"
    assert len(replay["ordered_measurement_ids"]) == 10
    assert len(set(replay["ordered_measurement_ids"])) == 10
    assert [item["prefix_size"] for item in replay["cumulative_results"]] == list(range(1, 11))
    assert replay["final_result"]["improvement_ratio"] == 0.8
    assert replay["final_result"]["worse_ratio"] == 0.1
    assert replay["final_result"]["improvement_wilson_90"]["lower"] >= 0.35
    assert replay["final_result"]["eligible"] is True
    assert replay["independent_sample_size"] == 10
    assert replay["final_challenger_eligible"] is True
    assert replay["blockers"] == []
    repeated_replay = governed_policy_candidate_service.replay_candidate(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        candidate_id=candidate["id"],
        actor_user_id=user.id,
    )
    assert repeated_replay["created"] is False
    assert db_session.query(GovernedPolicyReplay).count() == 1

    with pytest.raises(HTTPException) as missing_ack:
        governed_policy_candidate_service.review_candidate(
            db_session,
            tenant_id=tenant.id,
            organization_id=tenant.id,
            campaign_id=campaign.id,
            candidate_id=candidate["id"],
            actor_user_id=user.id,
            decision="approved_for_future_activation",
            replay_id=None,
            acknowledgements={
                "reviewed_rule_comparison": True,
                "understands_not_active": True,
            },
            note=None,
        )
    assert missing_ack.value.status_code == 422

    reviewed = governed_policy_candidate_service.review_candidate(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        candidate_id=candidate["id"],
        actor_user_id=user.id,
        decision="approved_for_future_activation",
        replay_id=None,
        acknowledgements={
            "reviewed_rule_comparison": True,
            "understands_not_active": True,
            "understands_no_causal_proof": True,
        },
        note="Owner reviewed the exact replay.",
    )
    assert reviewed["item"]["state"] == "approved_for_future_activation"
    assert reviewed["item"]["safety"]["live_policy_changed"] is False
    assert db_session.query(GovernedPolicyCandidate).count() == 1
    assert db_session.query(GovernedPolicyReplay).count() == 1
    assert db_session.query(GovernedPolicyDecision).count() == 1
    assert db_session.query(ExperimentAssignment).count() == assignments_before
    assert db_session.query(PolicyWeight).count() == weights_before

    with pytest.raises(HTTPException) as final_decision_locked:
        governed_policy_candidate_service.review_candidate(
            db_session,
            tenant_id=tenant.id,
            organization_id=tenant.id,
            campaign_id=campaign.id,
            candidate_id=candidate["id"],
            actor_user_id=user.id,
            decision="rejected",
            replay_id=None,
            acknowledgements={},
            note=None,
        )
    assert final_decision_locked.value.status_code == 409

    audits = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type.like("intelligence.governed_policy_%"))
        .all()
    )
    assert len(audits) == 3
    for row in audits:
        payload = json.loads(row.payload_json)
        assert payload["live_policy_changed"] is False
        assert payload["execution_enabled"] is False
        assert "Owner reviewed the exact replay" not in row.payload_json
        assert "ordered_measurement_ids" not in payload


def test_five_outcomes_can_create_candidate_but_stricter_replay_cannot_be_approved(
    db_session,
):
    tenant, user, campaign = _campaign(db_session, "Small Sample Campaign")
    _plan, protocol = _completed_protocol(db_session, tenant=tenant, user=user, campaign=campaign)
    _add_outcomes(
        db_session,
        tenant=tenant,
        user=user,
        campaign=campaign,
        classifications=["improved"] * 5,
    )
    item = governed_policy_candidate_service.create_candidate(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        protocol_id=protocol.id,
        actor_user_id=user.id,
    )["item"]
    replayed = governed_policy_candidate_service.replay_candidate(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        candidate_id=item["id"],
        actor_user_id=user.id,
    )["item"]
    assert replayed["latest_replay"]["status"] == "blocked"
    assert replayed["latest_replay"]["final_challenger_eligible"] is False
    assert replayed["latest_replay"]["blockers"][0]["code"] == ("needs_more_independent_results")
    assert replayed["latest_replay"]["final_result"]["checks"]["minimum_sample_met"] is False

    with pytest.raises(HTTPException) as blocked:
        governed_policy_candidate_service.review_candidate(
            db_session,
            tenant_id=tenant.id,
            organization_id=tenant.id,
            campaign_id=campaign.id,
            candidate_id=item["id"],
            actor_user_id=user.id,
            decision="approved_for_future_activation",
            replay_id=None,
            acknowledgements={
                "reviewed_rule_comparison": True,
                "understands_not_active": True,
                "understands_no_causal_proof": True,
            },
            note=None,
        )
    assert blocked.value.status_code == 409


def test_policy_candidate_requires_exactly_completed_protocol(db_session):
    tenant, user, campaign = _campaign(db_session, "Rollback Protocol Campaign")
    _plan, protocol = _completed_protocol(db_session, tenant=tenant, user=user, campaign=campaign)
    _add_outcomes(
        db_session,
        tenant=tenant,
        user=user,
        campaign=campaign,
        classifications=["improved"] * 5,
    )
    protocol.status = "rollback_verified"
    db_session.commit()

    with pytest.raises(HTTPException) as blocked:
        governed_policy_candidate_service.create_candidate(
            db_session,
            tenant_id=tenant.id,
            organization_id=tenant.id,
            campaign_id=campaign.id,
            protocol_id=protocol.id,
            actor_user_id=user.id,
        )
    assert blocked.value.status_code == 409
    assert db_session.query(GovernedPolicyCandidate).count() == 0


def test_policy_candidate_list_api_is_tenant_scoped(client, db_session):
    tenant, user, campaign = _campaign(db_session, "Scoped Candidate Campaign")
    _plan, protocol = _completed_protocol(db_session, tenant=tenant, user=user, campaign=campaign)
    _add_outcomes(
        db_session,
        tenant=tenant,
        user=user,
        campaign=campaign,
        classifications=["improved"] * 5,
    )
    governed_policy_candidate_service.create_candidate(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        protocol_id=protocol.id,
        actor_user_id=user.id,
    )
    login_a = client.post(
        "/api/v1/auth/login", json={"email": "a@example.com", "password": "pass-a"}
    )
    login_b = client.post(
        "/api/v1/auth/login", json={"email": "b@example.com", "password": "pass-b"}
    )
    headers_a = {"Authorization": f"Bearer {login_a.json()['data']['access_token']}"}
    headers_b = {"Authorization": f"Bearer {login_b.json()['data']['access_token']}"}

    response = client.get(
        f"/api/v1/intelligence/policy-candidates?campaign_id={campaign.id}",
        headers=headers_a,
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["count"] == 1
    item = payload["items"][0]
    assert item["id"]
    assert item["source_protocol_id"] == protocol.id
    assert item["source_plan_id"] == protocol.plan_id
    assert item["action_id"] == ACTION_ID
    assert item["metric_id"] == METRIC_ID
    assert item["measurement_contract_version"] == CONTRACT_VERSION
    assert item["champion_rules"]["minimum_independent_results"] == 5
    assert item["challenger_rules"]["minimum_independent_results"] == 10
    assert item["latest_replay"] is None
    assert item["state"] == "needs_replay"
    assert "candidate" not in item
    assert payload["safety"]["live_policy_activation_enabled"] is False
    assert payload["truth"]["provider_state"] == "saved_action_learning_replays"

    hidden = client.get(
        f"/api/v1/intelligence/policy-candidates?campaign_id={campaign.id}",
        headers=headers_b,
    )
    assert hidden.status_code == 404

    candidate_paths = {
        route.path
        for route in intelligence_router.routes
        if "policy-candidate" in getattr(route, "path", "")
    }
    assert candidate_paths == {
        "/intelligence/policy-candidates",
        "/intelligence/controlled-test-protocols/{protocol_id}/policy-candidate",
        "/intelligence/policy-candidates/{candidate_id}/replay",
        "/intelligence/policy-candidates/{candidate_id}/review",
    }
    assert all(
        verb not in path for path in candidate_paths for verb in ("activate", "promote", "execute")
    )
