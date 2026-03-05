from __future__ import annotations

from app.enums import StrategyRecommendationStatus
from app.intelligence.recommendation_execution_engine import execute_recommendation, schedule_execution
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.services.strategy_engine.automation_engine import evaluate_campaign_for_automation
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


def test_schedule_and_execute_recommendation_idempotently(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Exec Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Exec Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Exec Campaign',
        domain='exec.example',
    )

    rec = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='improve_internal_links',
        rationale='deterministic execution test',
        confidence=0.9,
        confidence_score=0.9,
        evidence_json='{}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(rec)
    db_session.commit()

    first = schedule_execution(rec.id, db=db_session)
    assert first is not None
    assert first.status == 'scheduled'

    second = schedule_execution(rec.id, db=db_session)
    assert second is not None
    assert second.id == first.id

    executed = execute_recommendation(first.id, db=db_session)
    assert executed is not None
    assert executed.status == 'completed'


def test_automation_engine_enqueues_for_approved_or_scheduled(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Auto Exec Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Auto Exec Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Auto Exec Campaign',
        domain='autoexec.example',
    )

    approved = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='fix_missing_title',
        rationale='approved',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='{}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    scheduled = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='optimize_gbp_profile',
        rationale='scheduled',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='{}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.SCHEDULED, StrategyRecommendationStatus),
    )
    db_session.add_all([approved, scheduled])
    db_session.commit()

    result = evaluate_campaign_for_automation(campaign.id, db_session)
    assert result['campaign_id'] == campaign.id

    count = (
        db_session.query(RecommendationExecution)
        .filter(RecommendationExecution.campaign_id == campaign.id)
        .count()
    )
    assert count >= 2
