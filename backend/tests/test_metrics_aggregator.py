from __future__ import annotations

import json
from datetime import UTC, datetime

from app.enums import StrategyRecommendationStatus
from app.intelligence.intelligence_metrics_aggregator import compute_campaign_metrics, compute_system_metrics
from app.models.audit_log import AuditLog
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.temporal import TemporalSignalSnapshot, TemporalSignalType
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


def test_compute_campaign_metrics_persists_snapshot(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Metrics Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Metrics Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Metrics Campaign',
        domain='metrics.example',
    )

    now = datetime.now(UTC)
    db_session.add_all(
        [
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='technical_issue_count',
                metric_value=4.0,
                observed_at=now,
                source='event:crawl.completed',
                confidence=1.0,
                version_hash='v1',
            ),
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='technical_issue_density',
                metric_value=0.15,
                observed_at=now,
                source='feature_store_v1',
                confidence=1.0,
                version_hash='v1',
            ),
        ]
    )

    rec = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='create_content_brief',
        rationale='metrics',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='[]',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(rec)
    db_session.flush()

    execution = RecommendationExecution(
        recommendation_id=rec.id,
        campaign_id=campaign.id,
        execution_type='create_content_brief',
        execution_payload='{}',
        idempotency_key=f'{rec.id}:create_content_brief:metrics',
        deterministic_hash='a' * 64,
        status='completed',
        attempt_count=1,
        executed_at=now,
    )
    db_session.add(execution)

    db_session.add_all(
        [
            RecommendationOutcome(
                recommendation_id=rec.id,
                campaign_id=campaign.id,
                metric_before=10,
                metric_after=12,
                delta=2,
                measured_at=now,
            ),
            RecommendationOutcome(
                recommendation_id=rec.id,
                campaign_id=campaign.id,
                metric_before=12,
                metric_after=11,
                delta=-1,
                measured_at=now,
            ),
        ]
    )

    db_session.add(
        AuditLog(
            tenant_id=tenant.id,
            event_type='recommendation.outcome_recorded',
            payload_json=json.dumps({'payload': {'campaign_id': campaign.id}}),
            created_at=now,
        )
    )
    db_session.commit()

    snapshot = compute_campaign_metrics(campaign.id, db=db_session)
    assert snapshot.campaign_id == campaign.id
    assert snapshot.signals_processed == 2
    assert snapshot.features_computed == 1
    assert snapshot.recommendations_generated == 1
    assert snapshot.executions_run == 1
    assert snapshot.positive_outcomes == 1
    assert snapshot.negative_outcomes == 1
    assert snapshot.policy_updates_applied == 1
    assert snapshot.patterns_detected >= 0


def test_compute_system_metrics_returns_rollups(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='System Metrics Tenant')
    org = create_test_org(tenant_id=tenant.id, name='System Metrics Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='System Metrics Campaign',
        domain='system-metrics.example',
    )

    compute_campaign_metrics(campaign.id, db=db_session)
    metrics = compute_system_metrics(db=db_session)

    assert metrics['campaigns_tracked'] >= 1
    assert 'recommendation_success_rate' in metrics
    assert 'execution_success_rate' in metrics
    assert 'pattern_discovery_rate' in metrics
    assert 'learning_velocity' in metrics
