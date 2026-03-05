from __future__ import annotations

from datetime import UTC, date, datetime

from app.intelligence.cohort_pattern_engine import discover_cohort_patterns
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.strategy_cohort_pattern import StrategyCohortPattern
from app.models.temporal import TemporalSignalSnapshot, TemporalSignalType
from tests.conftest import create_test_campaign


def test_discover_cohort_patterns_is_deterministic_with_filters(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Pattern Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Pattern Org')

    campaigns = [
        create_test_campaign(db_session, org.id, tenant_id=tenant.id, name=f'Pattern Campaign {idx}', domain='plumber.example')
        for idx in range(3)
    ]

    for idx, campaign in enumerate(campaigns):
        db_session.add_all(
            [
                CampaignDailyMetric(
                    organization_id=org.id,
                    campaign_id=campaign.id,
                    metric_date=date(2026, 3, 4),
                    sessions=100,
                    technical_issue_count=8,
                    normalization_version='analytics-v1',
                    deterministic_hash=f'p-a-{idx}',
                ),
                CampaignDailyMetric(
                    organization_id=org.id,
                    campaign_id=campaign.id,
                    metric_date=date(2026, 3, 5),
                    sessions=120,
                    technical_issue_count=6,
                    normalization_version='analytics-v1',
                    deterministic_hash=f'p-b-{idx}',
                ),
                TemporalSignalSnapshot(
                    campaign_id=campaign.id,
                    signal_type=TemporalSignalType.CUSTOM,
                    metric_name='internal_link_ratio',
                    metric_value=0.2,
                    observed_at=datetime.now(UTC),
                    source='feature_store_v1',
                    confidence=1.0,
                    version_hash=f'p-{idx}-1',
                ),
                TemporalSignalSnapshot(
                    campaign_id=campaign.id,
                    signal_type=TemporalSignalType.CUSTOM,
                    metric_name='ranking_velocity',
                    metric_value=0.25,
                    observed_at=datetime.now(UTC),
                    source='feature_store_v1',
                    confidence=1.0,
                    version_hash=f'p-{idx}-2',
                ),
                TemporalSignalSnapshot(
                    campaign_id=campaign.id,
                    signal_type=TemporalSignalType.CUSTOM,
                    metric_name='technical_issue_density',
                    metric_value=0.08,
                    observed_at=datetime.now(UTC),
                    source='feature_store_v1',
                    confidence=1.0,
                    version_hash=f'p-{idx}-3',
                ),
                TemporalSignalSnapshot(
                    campaign_id=campaign.id,
                    signal_type=TemporalSignalType.CUSTOM,
                    metric_name='content_growth_rate',
                    metric_value=0.12,
                    observed_at=datetime.now(UTC),
                    source='feature_store_v1',
                    confidence=1.0,
                    version_hash=f'p-{idx}-4',
                ),
            ]
        )

        rec = StrategyRecommendation(
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            recommendation_type='policy::internal::links',
            rationale='test',
            confidence=0.8,
            confidence_score=0.8,
            evidence_json='{}',
            rollback_plan_json='{}',
        )
        db_session.add(rec)
        db_session.flush()
        db_session.add(
            RecommendationOutcome(
                recommendation_id=rec.id,
                campaign_id=campaign.id,
                metric_before=10.0,
                metric_after=13.0,
                delta=3.0,
            )
        )

    db_session.commit()

    patterns = discover_cohort_patterns(db_session, persist=False)
    names = {item.pattern_name for item in patterns}
    assert 'low_internal_links_ranking_growth_after_linking' in names

    persisted = discover_cohort_patterns(db_session, persist=True)
    assert persisted

    stored = db_session.query(StrategyCohortPattern).count()
    assert stored >= len(persisted)
