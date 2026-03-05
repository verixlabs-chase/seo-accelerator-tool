from __future__ import annotations

from app.enums import StrategyRecommendationStatus
from app.intelligence.recommendation_execution_engine import approve_execution, execute_recommendation, schedule_execution
from app.models.intelligence import StrategyRecommendation
from app.models.intelligence_governance_policy import IntelligenceGovernancePolicy
from app.models.recommendation_execution import RecommendationExecution
from app.models.user import User
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


def _create_recommendation(db_session, tenant_id: str, campaign_id: str) -> StrategyRecommendation:
    row = StrategyRecommendation(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        recommendation_type='create_content_brief',
        rationale='approval test',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='[]',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_manual_approval_required_before_execution(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Approval Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Approval Org')
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Approval Campaign', domain='approval.example')

    db_session.add(
        IntelligenceGovernancePolicy(
            campaign_id=campaign.id,
            execution_type='create_content_brief',
            max_daily_executions=5,
            requires_manual_approval=True,
            risk_level='high',
            enabled=True,
        )
    )
    db_session.commit()

    recommendation = _create_recommendation(db_session, tenant.id, campaign.id)
    execution = schedule_execution(recommendation.id, db=db_session)
    assert isinstance(execution, RecommendationExecution)
    assert execution.status == 'pending'

    blocked = execute_recommendation(execution.id, db=db_session, dry_run=False)
    assert isinstance(blocked, RecommendationExecution)
    assert blocked.status == 'pending'
    assert blocked.last_error == 'manual_approval_required'

    approved = approve_execution(execution.id, approved_by='qa-user', db=db_session)
    assert approved is not None
    assert approved.approved_by == 'qa-user'
    assert approved.approved_at is not None

    executed = execute_recommendation(execution.id, db=db_session, dry_run=False)
    assert isinstance(executed, RecommendationExecution)
    assert executed.status in {'completed', 'failed'}


def test_approve_and_reject_endpoints(client, db_session, create_test_org) -> None:
    login = client.post('/api/v1/auth/login', json={'email': 'org-admin@example.com', 'password': 'pass-org-admin'})
    assert login.status_code == 200
    token = login.json()['data']['access_token']

    acting_user = db_session.query(User).filter(User.email == 'org-admin@example.com').first()
    assert acting_user is not None

    org = create_test_org(tenant_id=acting_user.tenant_id, name='Approval API Org')
    campaign = create_test_campaign(db_session, org.id, tenant_id=acting_user.tenant_id, name='Approval API Campaign', domain='approval-api.example')

    recommendation = _create_recommendation(db_session, acting_user.tenant_id, campaign.id)
    execution = schedule_execution(recommendation.id, db=db_session)
    assert isinstance(execution, RecommendationExecution)

    approve_resp = client.post(
        f'/api/v1/executions/{execution.id}/approve',
        json={'approved_by': 'api-approver'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()['data']['approved_by'] == 'api-approver'

    reject_resp = client.post(
        f'/api/v1/executions/{execution.id}/reject',
        json={'approved_by': 'api-reviewer'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()['data']['status'] == 'failed'
