from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from app.enums import StrategyRecommendationStatus
from app.models.action_plan import ActionPlanMeasurement, ActionPlanOccurrence
from app.models.audit_log import AuditLog
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.models.wordpress_automation_policy import WordPressAutomationPolicy
from app.services.wordpress_regression_monitor_service import (
    evaluate_wordpress_regression_pause,
)
from tests.conftest import create_test_campaign


def _measured_managed_action(
    db_session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    index: int,
    classification: str,
    measured_at: datetime,
) -> ActionPlanMeasurement:
    recommendation = StrategyRecommendation(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        recommendation_type="fix_missing_title",
        rationale=f"Managed website measurement {index}",
        confidence=0.9,
        confidence_score=0.9,
        evidence_json="{}",
        risk_tier=1,
        rollback_plan_json="{}",
        status=StrategyRecommendationStatus.EXECUTED,
    )
    db_session.add(recommendation)
    db_session.flush()
    execution = RecommendationExecution(
        recommendation_id=recommendation.id,
        campaign_id=campaign_id,
        execution_type="fix_missing_title",
        execution_payload=json.dumps(
            {
                "tenant_id": tenant_id,
                "organization_id": organization_id,
                "campaign_id": campaign_id,
                "managed_wordpress_automation": True,
                "automation_policy_version": 1,
            }
        ),
        idempotency_key=f"managed-regression-{index}",
        deterministic_hash=f"{index:064d}",
        status="completed",
        executed_at=measured_at - timedelta(days=14),
    )
    occurrence = ActionPlanOccurrence(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        business_location_id=None,
        recommendation_id=recommendation.id,
        action_id="technical.fix_missing_title",
        cadence="monthly",
        period_key=f"2026-08-{index:02d}",
        timezone="UTC",
        status="completed",
        lexicon_id="seo-intelligence-core",
        lexicon_version="1.0.0",
        content_hash=f"{index + 20:064d}",
        idempotency_key=f"regression-occurrence-{index}",
        completed_at=measured_at,
        created_at=measured_at - timedelta(days=15),
        updated_at=measured_at,
    )
    db_session.add_all([execution, occurrence])
    db_session.flush()
    measurement = ActionPlanMeasurement(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        business_location_id=None,
        occurrence_id=occurrence.id,
        recommendation_id=recommendation.id,
        action_id=occurrence.action_id,
        measurement_status="measured",
        outcome_status="did_not_help" if classification != "improved" else "helped",
        result_classification=classification,
        measurement_contract={
            "version": "2.0",
            "track": "website",
            "primary_metric_id": "technical.issue_density",
        },
        success_metric_ids=["technical.issue_density"],
        baseline_metrics=[{"metric_id": "technical.issue_density", "value": 1.0}],
        baseline_evidence=[],
        implementation_scope={"campaign_id": campaign_id},
        completion_proof=[],
        outcome_metrics=[
            {
                "metric_id": "technical.issue_density",
                "comparison": classification,
                "value": 2.0 if classification == "worse" else 0.5,
            }
        ],
        outcome_evidence=[],
        observation_window_days=14,
        evidence_window_start=measured_at - timedelta(days=14),
        evidence_window_end=measured_at,
        observation_due_at=measured_at,
        baseline_captured_at=measured_at - timedelta(days=28),
        work_completed_at=measured_at - timedelta(days=14),
        outcome_measured_at=measured_at,
        action_plan_hash=occurrence.content_hash,
        lexicon_id=occurrence.lexicon_id,
        lexicon_version=occurrence.lexicon_version,
        created_at=measured_at - timedelta(days=28),
        updated_at=measured_at,
    )
    db_session.add(measurement)
    db_session.flush()
    return measurement


def test_two_consecutive_measured_regressions_pause_only_the_site_policy(
    db_session,
    create_test_tenant,
    create_test_org,
) -> None:
    tenant = create_test_tenant(name="Regression Pause Tenant")
    organization = create_test_org(tenant_id=tenant.id, name="Regression Pause Org")
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant.id,
        name="Regression Pause Campaign",
        domain="regression-pause.example",
    )
    policy = WordPressAutomationPolicy(
        tenant_id=tenant.id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        automation_enabled=True,
        emergency_stop=False,
        allowed_action_types=["fix_missing_title"],
        allowed_url_prefixes=["https://regression-pause.example/"],
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
    db_session.add(policy)
    first = _measured_managed_action(
        db_session,
        tenant_id=tenant.id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        index=1,
        classification="worse",
        measured_at=datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
    )
    db_session.commit()

    first_result = evaluate_wordpress_regression_pause(
        db_session,
        measurement=first,
    )
    assert first_result["status"] == "watching"
    assert first_result["consecutive_regressions"] == 1
    assert first_result["causal_claim"] is False
    assert policy.emergency_stop is False

    second = _measured_managed_action(
        db_session,
        tenant_id=tenant.id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        index=2,
        classification="worse",
        measured_at=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
    )
    db_session.commit()

    paused = evaluate_wordpress_regression_pause(
        db_session,
        measurement=second,
    )

    assert paused["status"] == "paused"
    assert paused["consecutive_regressions"] == 2
    assert paused["causal_claim"] is False
    db_session.refresh(policy)
    assert policy.emergency_stop is True
    assert policy.paused_reason_code == "wordpress_repeated_measured_regression"
    assert policy.version == 2
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type
            == "wordpress.automation_policy.regression_paused"
        )
        .one()
    )
    audit_payload = json.loads(audit.payload_json)
    assert audit_payload["measurement_ids"] == paused["measurement_ids"]
    assert audit_payload["causal_claim"] is False


def test_a_non_regression_resets_the_consecutive_pause_count(
    db_session,
    create_test_tenant,
    create_test_org,
) -> None:
    tenant = create_test_tenant(name="Regression Reset Tenant")
    organization = create_test_org(tenant_id=tenant.id, name="Regression Reset Org")
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant.id,
        name="Regression Reset Campaign",
        domain="regression-reset.example",
    )
    policy = WordPressAutomationPolicy(
        tenant_id=tenant.id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        automation_enabled=True,
        emergency_stop=False,
        allowed_action_types=["fix_missing_title"],
        allowed_url_prefixes=["https://regression-reset.example/"],
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
    db_session.add(policy)
    for index, classification in ((1, "worse"), (2, "improved"), (3, "worse")):
        latest = _measured_managed_action(
            db_session,
            tenant_id=tenant.id,
            organization_id=organization.id,
            campaign_id=campaign.id,
            index=index + 10,
            classification=classification,
            measured_at=datetime(2026, 8, index * 4, 12, 0, tzinfo=UTC),
        )
    db_session.commit()

    result = evaluate_wordpress_regression_pause(
        db_session,
        measurement=latest,
    )

    assert result["status"] == "watching"
    assert result["consecutive_regressions"] == 1
    db_session.refresh(policy)
    assert policy.emergency_stop is False
