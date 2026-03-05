from __future__ import annotations

from app.enums import StrategyRecommendationStatus
from app.intelligence.recommendation_execution_engine import schedule_execution
from app.models.intelligence import StrategyRecommendation
from app.models.intelligence_governance_policy import IntelligenceGovernancePolicy
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


def _create_recommendation(db_session, tenant_id: str, campaign_id: str, rec_type: str) -> StrategyRecommendation:
    row = StrategyRecommendation(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        recommendation_type=rec_type,
        rationale='governance test',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='[]',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_execution_type_disabled_policy_blocks_scheduling(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Gov Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Gov Org')
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Gov Campaign', domain='gov.example')

    db_session.add(
        IntelligenceGovernancePolicy(
            campaign_id=campaign.id,
            execution_type='create_content_brief',
            max_daily_executions=10,
            requires_manual_approval=False,
            risk_level='low',
            enabled=False,
        )
    )
    db_session.commit()

    recommendation = _create_recommendation(db_session, tenant.id, campaign.id, 'create_content_brief')
    blocked = schedule_execution(recommendation.id, db=db_session)

    assert isinstance(blocked, dict)
    assert blocked['status'] == 'blocked'
    assert blocked['reason_code'] == 'execution_type_disabled'


def test_max_daily_executions_policy_is_enforced(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Gov Limit Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Gov Limit Org')
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Gov Limit Campaign', domain='gov-limit.example')

    db_session.add(
        IntelligenceGovernancePolicy(
            campaign_id=campaign.id,
            execution_type='create_content_brief',
            max_daily_executions=1,
            requires_manual_approval=False,
            risk_level='medium',
            enabled=True,
        )
    )
    db_session.commit()

    first_recommendation = _create_recommendation(db_session, tenant.id, campaign.id, 'create_content_brief')
    first_execution = schedule_execution(first_recommendation.id, db=db_session)
    assert first_execution is not None
    assert not isinstance(first_execution, dict)

    second_recommendation = _create_recommendation(db_session, tenant.id, campaign.id, 'create_content_brief')
    blocked = schedule_execution(second_recommendation.id, db=db_session)

    assert isinstance(blocked, dict)
    assert blocked['status'] == 'blocked'
    assert blocked['reason_code'] == 'max_daily_executions_exceeded'
