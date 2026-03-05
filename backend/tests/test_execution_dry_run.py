from __future__ import annotations

from app.enums import StrategyRecommendationStatus
from app.intelligence.recommendation_execution_engine import execute_recommendation, schedule_execution
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_outcome import RecommendationOutcome
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


REQUIRED_RESULT_KEYS = {
    'execution_type',
    'status',
    'actions',
    'artifacts',
    'metrics_to_measure',
    'notes',
}


def test_dry_run_returns_plan_and_does_not_create_outcome(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='DryRun Tenant')
    org = create_test_org(tenant_id=tenant.id, name='DryRun Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='DryRun Campaign',
        domain='dryrun.example',
    )

    rec = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='create_content_brief',
        rationale='dry run test',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='[]',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(rec)
    db_session.commit()

    execution = schedule_execution(rec.id, db=db_session)
    assert execution is not None

    before_outcomes = db_session.query(RecommendationOutcome).count()
    planned = execute_recommendation(execution.id, db=db_session, dry_run=True)
    assert isinstance(planned, dict)
    assert REQUIRED_RESULT_KEYS.issubset(planned.keys())
    assert planned['status'] == 'planned'

    refreshed = db_session.get(type(execution), execution.id)
    assert refreshed is not None
    assert refreshed.status == 'scheduled'
    after_outcomes = db_session.query(RecommendationOutcome).count()
    assert after_outcomes == before_outcomes
