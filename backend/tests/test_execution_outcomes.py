from __future__ import annotations

import json

from app.enums import StrategyRecommendationStatus
from app.intelligence.recommendation_execution_engine import record_execution_result, schedule_execution
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_outcome import RecommendationOutcome
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


def test_record_execution_result_creates_outcome(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Outcome Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Outcome Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Outcome Campaign',
        domain='outcome.example',
    )

    rec = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='create_content_brief',
        rationale='outcome test',
        confidence=0.9,
        confidence_score=0.9,
        evidence_json='{}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(rec)
    db_session.commit()

    execution = schedule_execution(rec.id, db=db_session)
    assert execution is not None

    result = {
        'metric_name': 'content_count',
        'metric_before': 10.0,
        'metric_after': 13.0,
        'delta': 3.0,
        'status': 'completed',
        'execution_type': execution.execution_type,
    }
    updated = record_execution_result(execution.id, result, db=db_session)
    assert updated is not None
    assert updated.status == 'completed'
    assert json.loads(updated.result_summary or '{}').get('delta') == 3.0

    outcome = (
        db_session.query(RecommendationOutcome)
        .filter(RecommendationOutcome.recommendation_id == rec.id)
        .order_by(RecommendationOutcome.measured_at.desc(), RecommendationOutcome.id.desc())
        .first()
    )
    assert outcome is not None
    assert outcome.delta == 3.0
