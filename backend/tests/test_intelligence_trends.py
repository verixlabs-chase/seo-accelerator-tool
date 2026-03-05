from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.enums import StrategyRecommendationStatus
from app.intelligence.intelligence_metrics_aggregator import compute_campaign_trends, compute_system_trends
from app.models.intelligence import StrategyRecommendation
from app.models.intelligence_metrics_snapshot import IntelligenceMetricsSnapshot
from app.models.recommendation_outcome import RecommendationOutcome
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


def test_campaign_trends_are_deterministic(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Trend Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Trend Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Trend Campaign',
        domain='trend.example',
    )

    recommendation = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='create_content_brief',
        rationale='trend test',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='[]',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(recommendation)
    db_session.flush()

    today = date.today()
    db_session.add_all(
        [
            IntelligenceMetricsSnapshot(
                campaign_id=campaign.id,
                metric_date=today - timedelta(days=1),
                signals_processed=3,
                features_computed=2,
                patterns_detected=1,
                recommendations_generated=2,
                executions_run=2,
                positive_outcomes=1,
                negative_outcomes=1,
                policy_updates_applied=1,
            ),
            IntelligenceMetricsSnapshot(
                campaign_id=campaign.id,
                metric_date=today,
                signals_processed=5,
                features_computed=4,
                patterns_detected=3,
                recommendations_generated=2,
                executions_run=2,
                positive_outcomes=2,
                negative_outcomes=0,
                policy_updates_applied=2,
            ),
            RecommendationOutcome(
                recommendation_id=recommendation.id,
                campaign_id=campaign.id,
                metric_before=10,
                metric_after=12,
                delta=2,
                measured_at=datetime.now(UTC),
            ),
        ]
    )
    db_session.commit()

    trends = compute_campaign_trends(campaign.id, db=db_session, days=2)
    assert trends['campaign_id'] == campaign.id
    assert len(trends['success_rate_over_time']) == 2
    assert trends['pattern_growth_rate'] == 2.0
    assert trends['learning_velocity'] == 1.5


def test_system_trends_include_required_rates(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='System Trend Tenant')
    org = create_test_org(tenant_id=tenant.id, name='System Trend Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='System Trend Campaign',
        domain='system-trend.example',
    )

    db_session.add(
        IntelligenceMetricsSnapshot(
            campaign_id=campaign.id,
            metric_date=date.today(),
            signals_processed=3,
            features_computed=2,
            patterns_detected=1,
            recommendations_generated=1,
            executions_run=1,
            positive_outcomes=1,
            negative_outcomes=0,
            policy_updates_applied=1,
        )
    )
    db_session.commit()

    trends = compute_system_trends(db=db_session, days=2)
    assert trends['window_days'] == 2
    assert 'success_rate_over_time' in trends
    assert 'pattern_growth_rate' in trends
    assert 'policy_weight_changes' in trends
