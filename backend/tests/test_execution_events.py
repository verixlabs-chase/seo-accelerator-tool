from __future__ import annotations

import json

from app.enums import StrategyRecommendationStatus
from app.intelligence.recommendation_execution_engine import execute_recommendation, schedule_execution
from app.models.audit_log import AuditLog
from app.models.intelligence import StrategyRecommendation
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


def test_execution_lifecycle_events_are_emitted(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Events Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Events Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Events Campaign',
        domain='events-exec.example',
    )

    rec = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='fix_missing_title',
        rationale='events test',
        confidence=0.9,
        confidence_score=0.9,
        evidence_json='[]',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(rec)
    db_session.commit()

    execution = schedule_execution(rec.id, db=db_session)
    assert execution is not None
    execute_recommendation(execution.id, db=db_session)

    rows = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.tenant_id == tenant.id,
            AuditLog.event_type.in_(['execution.scheduled', 'execution.started', 'execution.completed']),
        )
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        .all()
    )
    event_types = [row.event_type for row in rows]
    assert 'execution.scheduled' in event_types
    assert 'execution.started' in event_types
    assert 'execution.completed' in event_types

    for row in rows:
        envelope = json.loads(row.payload_json)
        payload = envelope.get('payload', {})
        assert payload.get('execution_id') == execution.id
        assert payload.get('recommendation_id') == rec.id
        assert payload.get('campaign_id') == campaign.id
        assert payload.get('execution_type') == execution.execution_type
        assert isinstance(payload.get('idempotency_key'), str)
        assert isinstance(payload.get('deterministic_hash'), str)
        assert payload.get('result_summary') is not None
