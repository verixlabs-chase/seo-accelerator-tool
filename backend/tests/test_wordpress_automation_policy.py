from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

from app.intelligence import recommendation_execution_engine as execution_engine
from app.enums import StrategyRecommendationStatus
from app.intelligence.recommendation_execution_engine import (
    execute_recommendation,
    schedule_execution,
)
from app.models.action_plan import ActionPlanMeasurement, ActionPlanOccurrence, ActionPlanStep
from app.models.audit_log import AuditLog
from app.models.intelligence import StrategyRecommendation
from app.models.organization import Organization
from app.models.platform_job import PlatformJob
from app.models.recommendation_execution import RecommendationExecution
from app.models.wordpress_automation_policy import WordPressAutomationPolicy
from app.models.wordpress_change_preview import WordPressChangePreview
from app.models.wordpress_site_connection import WordPressSiteConnection
from app.services import action_plan_measurement_service, durable_job_service, job_service
from app.services.wordpress_automation_policy_service import evaluate_wordpress_automation
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


MASTER_KEY_B64 = base64.b64encode(
    b"0123456789abcdef0123456789abcdef"
).decode("ascii")


def _recommendation(db_session, *, tenant_id: str, campaign_id: str) -> StrategyRecommendation:
    row = StrategyRecommendation(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        recommendation_type="fix_missing_title",
        rationale="Safe managed title update",
        confidence=0.9,
        confidence_score=0.9,
        evidence_json="{}",
        rollback_plan_json="{}",
        risk_tier=1,
        status=ensure_enum(
            StrategyRecommendationStatus.APPROVED,
            StrategyRecommendationStatus,
        ),
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_policy_api_starts_off_and_requires_a_connected_site(
    client,
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "pass-a"},
    )
    assert login.status_code == 200
    auth = login.json()["data"]
    token = auth["access_token"]
    tenant_id = auth["user"]["tenant_id"]
    organization = db_session.get(Organization, tenant_id)
    assert organization is not None
    organization.plan_type = "multi_location"
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant_id,
        name="Managed WordPress",
        domain="example.com",
    )
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    default_response = client.get(
        "/api/v1/wordpress-automation/policy",
        params={"campaign_id": campaign.id},
        headers=headers,
    )
    assert default_response.status_code == 200
    default_policy = default_response.json()["data"]["policy"]
    assert default_policy["automation_enabled"] is False
    assert default_policy["safe_default"] is True
    assert default_policy["monthly_action_limit"] == 0
    assert default_policy["requires_manual_approval"] is True

    policy_payload = {
        "automation_enabled": True,
        "allowed_action_types": ["fix_missing_title"],
        "allowed_url_prefixes": ["https://example.com/services"],
        "schedule_timezone": "America/Chicago",
        "schedule_days": [0, 1, 2, 3, 4, 5, 6],
        "window_start_local": "00:00",
        "window_end_local": "23:59",
        "blackout_windows": [],
        "monthly_action_limit": 12,
        "risk_tier_ceiling": 1,
        "requires_manual_approval": True,
        "emergency_stop": False,
    }
    disconnected = client.put(
        "/api/v1/wordpress-automation/policy",
        params={"campaign_id": campaign.id},
        json=policy_payload,
        headers=headers,
    )
    assert disconnected.status_code == 409
    assert "wordpress_site_connection_required" in str(disconnected.json())

    start = client.post(
        "/api/v1/provider-health/wordpress-pairing/start",
        params={"campaign_id": campaign.id},
        headers=headers,
    )
    assert start.status_code == 200
    exchange = client.post(
        "/api/v1/provider-health/wordpress-pairing/exchange",
        json={
            "pairing_code": start.json()["data"]["pairing_code"],
            "site_url": "https://example.com",
            "plugin_version": "1.5.1",
        },
    )
    assert exchange.status_code == 200

    saved = client.put(
        "/api/v1/wordpress-automation/policy",
        params={"campaign_id": campaign.id},
        json=policy_payload,
        headers=headers,
    )
    assert saved.status_code == 200
    saved_policy = saved.json()["data"]["policy"]
    assert saved_policy["automation_enabled"] is True
    assert saved_policy["allowed_action_types"] == ["fix_missing_title"]
    assert saved_policy["allowed_url_prefixes"] == ["https://example.com/services"]
    assert saved_policy["version"] == 1
    assert saved_policy["acknowledged_by"]
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "wordpress.automation_policy.updated")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit is not None
    assert campaign.id in audit.payload_json


def test_policy_decision_enforces_risk_scope_and_emergency_stop(
    db_session,
    create_test_tenant,
    create_test_org,
) -> None:
    tenant = create_test_tenant(name="Managed Policy Tenant")
    organization = create_test_org(tenant_id=tenant.id, name="Managed Policy Org")
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant.id,
        name="Managed Policy Campaign",
        domain="example.com",
    )
    policy = WordPressAutomationPolicy(
        tenant_id=tenant.id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        automation_enabled=True,
        emergency_stop=False,
        allowed_action_types=["fix_missing_title"],
        allowed_url_prefixes=["https://example.com/services"],
        schedule_timezone="UTC",
        schedule_days=[0, 1, 2, 3, 4, 5, 6],
        window_start_local="00:00",
        window_end_local="23:59",
        blackout_windows=[],
        monthly_action_limit=5,
        risk_tier_ceiling=1,
        requires_manual_approval=True,
        version=1,
    )
    connection = WordPressSiteConnection(
        tenant_id=tenant.id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        site_url="https://example.com",
        status="connected",
        plugin_version="1.5.1",
        paired_at=datetime.now(UTC),
    )
    db_session.add_all([policy, connection])
    db_session.commit()
    observed_at = datetime(2026, 8, 13, 15, 0, tzinfo=UTC)

    allowed = evaluate_wordpress_automation(
        db_session,
        campaign_id=campaign.id,
        execution_type="fix_missing_title",
        risk_tier=1,
        affected_urls=["https://example.com/services/plumbing"],
        at=observed_at,
    )
    assert allowed.allowed is True
    assert allowed.requires_manual_approval is True

    wrong_scope = evaluate_wordpress_automation(
        db_session,
        campaign_id=campaign.id,
        execution_type="fix_missing_title",
        risk_tier=1,
        affected_urls=["https://example.com/about"],
        at=observed_at,
    )
    assert wrong_scope.allowed is False
    assert wrong_scope.reason_code == "wordpress_automation_url_not_allowed"

    high_risk = evaluate_wordpress_automation(
        db_session,
        campaign_id=campaign.id,
        execution_type="fix_missing_title",
        risk_tier=2,
        at=observed_at,
    )
    assert high_risk.reason_code == "wordpress_automation_risk_too_high"

    policy.emergency_stop = True
    db_session.commit()
    stopped = evaluate_wordpress_automation(
        db_session,
        campaign_id=campaign.id,
        execution_type="fix_missing_title",
        risk_tier=1,
        at=observed_at,
    )
    assert stopped.reason_code == "wordpress_automation_emergency_stop"


def test_autonomous_wordpress_scheduling_fails_closed_without_owner_policy(
    db_session,
    create_test_tenant,
    create_test_org,
) -> None:
    tenant = create_test_tenant(name="Fail Closed Tenant")
    organization = create_test_org(tenant_id=tenant.id, name="Fail Closed Org")
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant.id,
        name="Fail Closed Campaign",
        domain="example.com",
    )
    recommendation = _recommendation(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
    )
    managed = schedule_execution(
        recommendation.id,
        db=db_session,
        managed_automation=True,
    )
    assert isinstance(managed, dict)
    assert managed["reason_code"] == "wordpress_automation_not_enabled"

    manual = schedule_execution(recommendation.id, db=db_session)
    assert isinstance(manual, RecommendationExecution)
    assert manual.idempotency_key.endswith(datetime.now(UTC).date().isoformat())


def test_low_risk_managed_execution_auto_approves_its_exact_scoped_preview(
    db_session,
    create_test_tenant,
    create_test_org,
    monkeypatch,
) -> None:
    tenant = create_test_tenant(name="Managed Preview Tenant")
    organization = create_test_org(
        tenant_id=tenant.id,
        name="Managed Preview Org",
    )
    organization.plan_type = "multi_location"
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant.id,
        name="Managed Preview Campaign",
        domain="managed-preview.example",
    )
    db_session.add_all(
        [
            WordPressSiteConnection(
                tenant_id=tenant.id,
                organization_id=organization.id,
                campaign_id=campaign.id,
                site_url="https://managed-preview.example",
                status="connected",
                plugin_version="1.5.1",
                paired_at=datetime.now(UTC),
            ),
            WordPressAutomationPolicy(
                tenant_id=tenant.id,
                organization_id=organization.id,
                campaign_id=campaign.id,
                automation_enabled=True,
                emergency_stop=False,
                allowed_action_types=["fix_missing_title"],
                allowed_url_prefixes=["https://managed-preview.example/"],
                schedule_timezone="UTC",
                schedule_days=[0, 1, 2, 3, 4, 5, 6],
                window_start_local="00:00",
                window_end_local="23:59",
                blackout_windows=[],
                monthly_action_limit=1,
                risk_tier_ceiling=1,
                requires_manual_approval=False,
                version=1,
            ),
        ]
    )
    recommendation = _recommendation(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
    )
    recommendation.evidence_json = json.dumps(
        {
            "action_id": "organic.rewrite_search_snippet",
            "target_url": "/",
        }
    )
    db_session.commit()

    execution = schedule_execution(
        recommendation.id,
        db=db_session,
        managed_automation=True,
    )
    assert isinstance(execution, RecommendationExecution)
    assert execution.status == "scheduled"
    assert execution.approved_by is None

    completed = execute_recommendation(execution.id, db=db_session)

    assert isinstance(completed, RecommendationExecution)
    assert completed.status == "completed"
    assert completed.approved_by == "InsightOS policy v1"
    preview = (
        db_session.query(WordPressChangePreview)
        .filter(WordPressChangePreview.execution_id == execution.id)
        .one()
    )
    assert preview.status == "approved"
    assert preview.approved_by == "InsightOS policy v1"
    assert preview.snapshot["affected_urls"] == ["/"]
    validation = preview.snapshot["managed_content_validation"]
    assert validation["status"] == "passed"
    assert validation["validator_version"] == "wordpress-managed-content-v1"
    assert validation["traceability"]["recommendation_id"] == recommendation.id
    assert validation["traceability"]["automation_policy_version"] == 1
    result_summary = json.loads(completed.result_summary or "{}")
    follow_up = result_summary["post_change_measurement"]
    assert follow_up["status"] == "scheduled"
    assert follow_up["causal_claim"] is False
    occurrence = db_session.get(ActionPlanOccurrence, follow_up["occurrence_id"])
    measurement = db_session.get(ActionPlanMeasurement, follow_up["measurement_id"])
    assert occurrence is not None
    assert occurrence.status == "waiting_for_results"
    assert measurement is not None
    assert measurement.measurement_status == "waiting_for_results"
    baseline_captured_at = measurement.baseline_captured_at
    executed_at = completed.executed_at
    observation_due_at = measurement.observation_due_at
    assert executed_at is not None
    assert observation_due_at is not None
    if baseline_captured_at.tzinfo is None:
        baseline_captured_at = baseline_captured_at.replace(tzinfo=UTC)
    if executed_at.tzinfo is None:
        executed_at = executed_at.replace(tzinfo=UTC)
    if observation_due_at.tzinfo is None:
        observation_due_at = observation_due_at.replace(tzinfo=UTC)
    assert baseline_captured_at <= executed_at
    assert observation_due_at > executed_at
    assert measurement.measurement_contract["managed_wordpress_execution"][
        "execution_id"
    ] == completed.id
    assert measurement.measurement_contract["managed_wordpress_execution"][
        "causal_claim"
    ] is False
    steps = (
        db_session.query(ActionPlanStep)
        .filter(ActionPlanStep.occurrence_id == occurrence.id)
        .all()
    )
    assert steps
    assert all(step.status == "done" for step in steps if step.required)
    follow_up_job = db_session.get(PlatformJob, follow_up["job_id"])
    assert follow_up_job is not None
    assert follow_up_job.job_type == "wordpress.post_change_measurement"
    assert follow_up_job.status == "queued"
    assert follow_up_job.available_at == measurement.observation_due_at

    measured_calls: list[str] = []

    def _evaluate_outcome(db, **kwargs):  # noqa: ANN001
        measured_calls.append(str(kwargs["occurrence_id"]))
        return {
            "measurement_id": measurement.id,
            "measurement_status": "measured",
            "result_classification": "not_enough_information",
        }

    monkeypatch.setattr(
        action_plan_measurement_service,
        "evaluate_action_plan_outcome",
        _evaluate_outcome,
    )
    job_service.start_job(db_session, follow_up_job.id, worker_id="test-worker")
    db_session.commit()
    processed = durable_job_service.execute_claimed_job(
        db_session,
        job_id=follow_up_job.id,
    )
    assert processed["status"] == "completed"
    assert measured_calls == [occurrence.id]


def test_managed_execution_blocks_unverified_business_claim_before_delivery(
    db_session,
    create_test_tenant,
    create_test_org,
) -> None:
    tenant = create_test_tenant(name="Managed Claim Tenant")
    organization = create_test_org(tenant_id=tenant.id, name="Managed Claim Org")
    organization.plan_type = "multi_location"
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant.id,
        name="Managed Claim Campaign",
        domain="managed-claim.example",
    )
    db_session.add_all(
        [
            WordPressSiteConnection(
                tenant_id=tenant.id,
                organization_id=organization.id,
                campaign_id=campaign.id,
                site_url="https://managed-claim.example",
                status="connected",
                plugin_version="1.5.1",
                paired_at=datetime.now(UTC),
            ),
            WordPressAutomationPolicy(
                tenant_id=tenant.id,
                organization_id=organization.id,
                campaign_id=campaign.id,
                automation_enabled=True,
                emergency_stop=False,
                allowed_action_types=["fix_missing_title"],
                allowed_url_prefixes=["https://managed-claim.example/"],
                schedule_timezone="UTC",
                schedule_days=[0, 1, 2, 3, 4, 5, 6],
                window_start_local="00:00",
                window_end_local="23:59",
                blackout_windows=[],
                monthly_action_limit=2,
                risk_tier_ceiling=1,
                requires_manual_approval=False,
                version=3,
            ),
        ]
    )
    recommendation = _recommendation(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
    )
    recommendation.evidence_json = json.dumps(
        {
            "target_url": "/",
            "meta_title": "Guaranteed top-rated service in town",
            "meta_description": "Choose our award-winning team.",
        }
    )
    db_session.commit()

    execution = schedule_execution(
        recommendation.id,
        db=db_session,
        managed_automation=True,
    )
    assert isinstance(execution, RecommendationExecution)

    blocked = execute_recommendation(execution.id, db=db_session)

    assert isinstance(blocked, RecommendationExecution)
    assert blocked.status == "pending"
    assert blocked.last_error == "wordpress_content_validation_failed"
    assert blocked.approved_by is None
    preview = (
        db_session.query(WordPressChangePreview)
        .filter(WordPressChangePreview.execution_id == execution.id)
        .one()
    )
    assert preview.status == "blocked"
    validation = preview.snapshot["managed_content_validation"]
    assert validation["status"] == "blocked"
    assert {
        issue["code"] for issue in validation["blocking_issues"]
    } == {"wordpress_content_unverified_claim"}
    assert validation["traceability"]["automation_policy_version"] == 3


def test_managed_draft_requires_confirmed_service_and_current_page_inventory(
    db_session,
    create_test_tenant,
    create_test_org,
) -> None:
    tenant = create_test_tenant(name="Managed Draft Tenant")
    organization = create_test_org(tenant_id=tenant.id, name="Managed Draft Org")
    organization.plan_type = "multi_location"
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant.id,
        name="Managed Draft Campaign",
        domain="managed-draft.example",
    )
    db_session.add_all(
        [
            WordPressSiteConnection(
                tenant_id=tenant.id,
                organization_id=organization.id,
                campaign_id=campaign.id,
                site_url="https://managed-draft.example",
                status="connected",
                plugin_version="1.5.1",
                paired_at=datetime.now(UTC),
            ),
            WordPressAutomationPolicy(
                tenant_id=tenant.id,
                organization_id=organization.id,
                campaign_id=campaign.id,
                automation_enabled=True,
                emergency_stop=False,
                allowed_action_types=["create_content_brief"],
                allowed_url_prefixes=["https://managed-draft.example/services"],
                schedule_timezone="UTC",
                schedule_days=[0, 1, 2, 3, 4, 5, 6],
                window_start_local="00:00",
                window_end_local="23:59",
                blackout_windows=[],
                monthly_action_limit=2,
                risk_tier_ceiling=1,
                requires_manual_approval=False,
                version=2,
            ),
        ]
    )
    recommendation = _recommendation(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
    )
    recommendation.recommendation_type = "content page"
    recommendation.rationale = "Explain appliance removal services."
    recommendation.evidence_json = json.dumps(
        {
            "content_title": "Appliance Removal",
            "content_slug": "services-appliance-removal",
            "content_target_url": "/services/appliance-removal",
        }
    )
    db_session.commit()

    execution = schedule_execution(
        recommendation.id,
        db=db_session,
        managed_automation=True,
    )
    assert isinstance(execution, RecommendationExecution)

    blocked = execute_recommendation(execution.id, db=db_session)

    assert isinstance(blocked, RecommendationExecution)
    assert blocked.status == "pending"
    assert blocked.last_error == "wordpress_content_validation_failed"
    preview = (
        db_session.query(WordPressChangePreview)
        .filter(WordPressChangePreview.execution_id == execution.id)
        .one()
    )
    issue_codes = {
        issue["code"]
        for issue in preview.snapshot["managed_content_validation"]["blocking_issues"]
    }
    assert "wordpress_confirmed_service_required" in issue_codes
    assert "wordpress_content_inventory_required" in issue_codes


def test_managed_preview_stays_pending_when_exact_url_is_outside_saved_scope(
    db_session,
    create_test_tenant,
    create_test_org,
) -> None:
    tenant = create_test_tenant(name="Managed Scope Tenant")
    organization = create_test_org(tenant_id=tenant.id, name="Managed Scope Org")
    organization.plan_type = "multi_location"
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant.id,
        name="Managed Scope Campaign",
        domain="managed-scope.example",
    )
    db_session.add_all(
        [
            WordPressSiteConnection(
                tenant_id=tenant.id,
                organization_id=organization.id,
                campaign_id=campaign.id,
                site_url="https://managed-scope.example",
                status="connected",
                plugin_version="1.5.1",
                paired_at=datetime.now(UTC),
            ),
            WordPressAutomationPolicy(
                tenant_id=tenant.id,
                organization_id=organization.id,
                campaign_id=campaign.id,
                automation_enabled=True,
                emergency_stop=False,
                allowed_action_types=["fix_missing_title"],
                allowed_url_prefixes=["https://managed-scope.example/services"],
                schedule_timezone="UTC",
                schedule_days=[0, 1, 2, 3, 4, 5, 6],
                window_start_local="00:00",
                window_end_local="23:59",
                blackout_windows=[],
                monthly_action_limit=5,
                risk_tier_ceiling=1,
                requires_manual_approval=False,
                version=1,
            ),
        ]
    )
    recommendation = _recommendation(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
    )
    execution = schedule_execution(
        recommendation.id,
        db=db_session,
        managed_automation=True,
    )
    assert isinstance(execution, RecommendationExecution)

    blocked = execute_recommendation(execution.id, db=db_session)

    assert isinstance(blocked, RecommendationExecution)
    assert blocked.status == "pending"
    assert blocked.last_error == "wordpress_automation_url_not_allowed"
    assert blocked.approved_by is None
    preview = (
        db_session.query(WordPressChangePreview)
        .filter(WordPressChangePreview.execution_id == execution.id)
        .one()
    )
    assert preview.status == "ready"
    assert preview.approved_by is None


def test_failed_public_verification_pauses_further_managed_updates(
    db_session,
    create_test_tenant,
    create_test_org,
    monkeypatch,
) -> None:
    tenant = create_test_tenant(name="Managed Pause Tenant")
    organization = create_test_org(tenant_id=tenant.id, name="Managed Pause Org")
    organization.plan_type = "multi_location"
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant.id,
        name="Managed Pause Campaign",
        domain="managed-pause.example",
    )
    policy = WordPressAutomationPolicy(
        tenant_id=tenant.id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        automation_enabled=True,
        emergency_stop=False,
        allowed_action_types=["fix_missing_title"],
        allowed_url_prefixes=["https://managed-pause.example/"],
        schedule_timezone="UTC",
        schedule_days=[0, 1, 2, 3, 4, 5, 6],
        window_start_local="00:00",
        window_end_local="23:59",
        blackout_windows=[],
        monthly_action_limit=5,
        risk_tier_ceiling=1,
        requires_manual_approval=False,
        version=1,
    )
    db_session.add_all(
        [
            policy,
            WordPressSiteConnection(
                tenant_id=tenant.id,
                organization_id=organization.id,
                campaign_id=campaign.id,
                site_url="https://managed-pause.example",
                status="connected",
                plugin_version="1.5.1",
                paired_at=datetime.now(UTC),
            ),
        ]
    )
    recommendation = _recommendation(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
    )
    execution = schedule_execution(
        recommendation.id,
        db=db_session,
        managed_automation=True,
    )
    assert isinstance(execution, RecommendationExecution)

    def failed_public_check(db, *, execution, mutations):  # noqa: ANN001
        results = [
            {
                "mutation_id": mutation["mutation_id"],
                "status": "applied",
                "mutation_type": mutation["action"],
                "target_url": mutation["target_url"],
                "before_state": {"value": "before"},
                "after_state": {"value": "after"},
                "rollback_payload": {"restore": "before"},
            }
            for mutation in mutations
        ]
        return {
            "provider_name": "wordpress_plugin",
            "delivery_mode": "wordpress_plugin",
            "results": results,
            "public_verification": {
                "passed": False,
                "checks_total": len(results),
                "checks_passed": 0,
                "checks_failed": len(results),
                "pages_checked": 1,
                "rollback_available": True,
                "results": [],
            },
        }

    monkeypatch.setattr(execution_engine, "apply_mutations", failed_public_check)
    failed = execute_recommendation(execution.id, db=db_session)

    assert isinstance(failed, RecommendationExecution)
    assert failed.status == "failed"
    assert failed.result_summary is not None
    assert '"managed_automation_paused": true' in failed.result_summary
    db_session.refresh(policy)
    assert policy.emergency_stop is True
    assert policy.paused_reason_code == "wordpress_public_verification_failed"
    assert policy.paused_execution_id == execution.id
    assert policy.paused_at is not None
    assert policy.version == 2

    later_recommendation = _recommendation(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
    )
    blocked = schedule_execution(
        later_recommendation.id,
        db=db_session,
        managed_automation=True,
    )
    assert isinstance(blocked, dict)
    assert blocked["reason_code"] == "wordpress_automation_emergency_stop"
