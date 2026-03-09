from __future__ import annotations

from app.enums import StrategyRecommendationStatus
from app.intelligence.recommendation_execution_engine import execute_recommendation, rollback_execution, schedule_execution
from app.models.execution_mutation import ExecutionMutation
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


def _recommendation(db_session, *, tenant_id: str, campaign_id: str, recommendation_type: str) -> StrategyRecommendation:
    row = StrategyRecommendation(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        recommendation_type=recommendation_type,
        rationale='mutation execution test',
        confidence=0.9,
        confidence_score=0.9,
        evidence_json='{}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_execution_persists_mutation_audit_rows(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Mutation Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Mutation Org')
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Mutation Campaign', domain='mutation.example')
    recommendation = _recommendation(db_session, tenant_id=tenant.id, campaign_id=campaign.id, recommendation_type='fix_missing_title')
    execution = schedule_execution(recommendation.id, db=db_session)
    assert isinstance(execution, RecommendationExecution)
    completed = execute_recommendation(execution.id, db=db_session)
    assert isinstance(completed, RecommendationExecution)
    assert completed.status == 'completed'
    rows = db_session.query(ExecutionMutation).filter(ExecutionMutation.execution_id == execution.id).all()
    assert len(rows) == 2
    assert {row.mutation_type for row in rows} == {'update_meta_title', 'update_meta_description'}
    for row in rows:
        assert row.before_state is not None
        assert row.after_state is not None
        assert row.rollback_payload is not None
        assert row.status == 'applied'


def test_execution_can_be_rolled_back(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Rollback Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Rollback Org')
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Rollback Campaign', domain='rollback.example')
    recommendation = _recommendation(db_session, tenant_id=tenant.id, campaign_id=campaign.id, recommendation_type='publish_schema_markup')
    execution = schedule_execution(recommendation.id, db=db_session)
    assert isinstance(execution, RecommendationExecution)
    completed = execute_recommendation(execution.id, db=db_session)
    assert isinstance(completed, RecommendationExecution)
    assert completed.status == 'completed'
    rolled_back = rollback_execution(execution.id, requested_by='tester', db=db_session)
    assert isinstance(rolled_back, RecommendationExecution)
    assert rolled_back.status == 'rolled_back'
    assert rolled_back.rolled_back_at is not None
    rows = db_session.query(ExecutionMutation).filter(ExecutionMutation.execution_id == execution.id).all()
    assert rows
    assert all(row.status == 'rolled_back' for row in rows)
    assert all(row.rolled_back_at is not None for row in rows)
