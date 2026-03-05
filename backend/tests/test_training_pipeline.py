from datetime import UTC, date, datetime

from app.intelligence.digital_twin.models.model_registry import reset_model_registry
from app.intelligence.digital_twin.models.training_pipeline import train_prediction_models
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.strategy_cohort_pattern import StrategyCohortPattern
from app.models.temporal import TemporalSignalSnapshot, TemporalSignalType
from tests.conftest import create_test_campaign


def test_training_pipeline_updates_model_registry(db_session, create_test_tenant, create_test_org) -> None:
    reset_model_registry()

    tenant = create_test_tenant(name='Training Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Training Org')
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Training Campaign', domain='train.example')

    recommendation = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='internal_linking',
        rationale='Increase internal links on key pages',
        confidence=0.7,
        confidence_score=0.7,
        evidence_json='[]',
        risk_tier=1,
        rollback_plan_json='{}',
        idempotency_key='train-1',
    )
    db_session.add(recommendation)
    db_session.flush()

    db_session.add(
        RecommendationOutcome(
            recommendation_id=recommendation.id,
            campaign_id=campaign.id,
            metric_before=10.0,
            metric_after=12.5,
            delta=2.5,
            measured_at=datetime.now(UTC),
        )
    )

    db_session.add(
        CampaignDailyMetric(
            organization_id=org.id,
            campaign_id=campaign.id,
            metric_date=date.today(),
            avg_position=8.5,
            sessions=120,
            technical_issue_count=5,
            deterministic_hash='training-metric-1',
        )
    )

    db_session.add(
        StrategyCohortPattern(
            pattern_name='high_content_velocity_traffic_growth',
            feature_name='content_growth_rate',
            cohort_definition='general_small_sites',
            pattern_strength=0.7,
            support_count=12,
            confidence=0.82,
        )
    )

    db_session.add(
        TemporalSignalSnapshot(
            campaign_id=campaign.id,
            signal_type=TemporalSignalType.CUSTOM,
            metric_name='ranking_velocity',
            metric_value=0.12,
            observed_at=datetime.now(UTC),
            source='test_training_pipeline',
            confidence=0.9,
            version_hash='train-snapshot-1',
        )
    )

    db_session.commit()

    result = train_prediction_models(db_session)

    assert result['trained'] is True
    assert result['samples']['recommendation_outcomes'] == 1
    assert result['samples']['campaign_daily_metrics'] == 1
    assert result['samples']['strategy_cohort_patterns'] == 1
    assert result['samples']['temporal_signal_snapshots'] >= 1

    coefficients = result['coefficients']
    assert coefficients['internal_links_added'] > 0.0
    assert coefficients['pages_added'] > 0.0
    assert coefficients['issues_fixed'] > 0.0

    assert result['model_registry']['rank_model_version'].startswith('v1-')
    assert result['model_registry']['traffic_factor'] >= 0.03
