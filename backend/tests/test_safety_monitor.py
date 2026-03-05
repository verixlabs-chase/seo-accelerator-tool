from __future__ import annotations

from datetime import UTC, datetime

from app.enums import StrategyRecommendationStatus
from app.intelligence.recommendation_execution_engine import schedule_execution
from app.intelligence.safety_monitor import evaluate_and_apply_safety_breaker, is_safety_paused
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.models.recommendation_outcome import RecommendationOutcome
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


def _create_recommendation(db_session, tenant_id: str, campaign_id: str, rec_type: str = 'create_content_brief') -> StrategyRecommendation:
    row = StrategyRecommendation(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        recommendation_type=rec_type,
        rationale='safety test',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='[]',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_safety_breaker_triggers_and_blocks_new_scheduling(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Safety Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Safety Org')
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Safety Campaign', domain='safety.example')

    recommendation = _create_recommendation(db_session, tenant.id, campaign.id)
    now = datetime.now(UTC)

    db_session.add_all(
        [
            RecommendationExecution(
                recommendation_id=recommendation.id,
                campaign_id=campaign.id,
                execution_type='create_content_brief',
                execution_payload='{}',
                idempotency_key='safety-fail-1',
                deterministic_hash='a' * 64,
                status='failed',
                attempt_count=1,
                created_at=now,
            ),
            RecommendationExecution(
                recommendation_id=recommendation.id,
                campaign_id=campaign.id,
                execution_type='create_content_brief',
                execution_payload='{}',
                idempotency_key='safety-fail-2',
                deterministic_hash='b' * 64,
                status='failed',
                attempt_count=1,
                created_at=now,
            ),
            RecommendationExecution(
                recommendation_id=recommendation.id,
                campaign_id=campaign.id,
                execution_type='create_content_brief',
                execution_payload='{}',
                idempotency_key='safety-fail-3',
                deterministic_hash='c' * 64,
                status='failed',
                attempt_count=1,
                created_at=now,
            ),
            RecommendationExecution(
                recommendation_id=recommendation.id,
                campaign_id=campaign.id,
                execution_type='create_content_brief',
                execution_payload='{}',
                idempotency_key='safety-complete-1',
                deterministic_hash='d' * 64,
                status='completed',
                attempt_count=1,
                created_at=now,
            ),
            RecommendationOutcome(
                recommendation_id=recommendation.id,
                campaign_id=campaign.id,
                metric_before=10,
                metric_after=8,
                delta=-2,
                measured_at=now,
            ),
            RecommendationOutcome(
                recommendation_id=recommendation.id,
                campaign_id=campaign.id,
                metric_before=8,
                metric_after=7,
                delta=-1,
                measured_at=now,
            ),
            RecommendationOutcome(
                recommendation_id=recommendation.id,
                campaign_id=campaign.id,
                metric_before=7,
                metric_after=6,
                delta=-1,
                measured_at=now,
            ),
        ]
    )
    db_session.commit()

    safety = evaluate_and_apply_safety_breaker(db_session, tenant_id=tenant.id)
    assert safety['triggered'] is True
    assert 'execution_failure_rate_exceeded' in safety['reasons']
    assert is_safety_paused(db_session) is True

    new_recommendation = _create_recommendation(db_session, tenant.id, campaign.id, rec_type='create_content_brief')
    db_session.commit()

    blocked = schedule_execution(new_recommendation.id, db=db_session)
    assert isinstance(blocked, dict)
    assert blocked['reason_code'] == 'safety_circuit_breaker_active'
