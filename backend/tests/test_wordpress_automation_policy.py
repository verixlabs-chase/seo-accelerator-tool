from __future__ import annotations

import base64
from datetime import UTC, datetime

from app.enums import StrategyRecommendationStatus
from app.intelligence.recommendation_execution_engine import (
    execute_recommendation,
    schedule_execution,
)
from app.models.audit_log import AuditLog
from app.models.intelligence import StrategyRecommendation
from app.models.organization import Organization
from app.models.recommendation_execution import RecommendationExecution
from app.models.wordpress_automation_policy import WordPressAutomationPolicy
from app.models.wordpress_change_preview import WordPressChangePreview
from app.models.wordpress_site_connection import WordPressSiteConnection
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
