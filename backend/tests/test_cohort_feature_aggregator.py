from __future__ import annotations

from datetime import UTC, date, datetime

from app.intelligence.cohort_feature_aggregator import aggregate_feature_profiles, build_cohort_rows
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.temporal import TemporalSignalSnapshot, TemporalSignalType
from tests.conftest import create_test_campaign


def test_build_cohort_rows_and_aggregate_profiles(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Cohort Agg Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Cohort Agg Org')

    campaigns = [
        create_test_campaign(db_session, org.id, tenant_id=tenant.id, name=f'Campaign {idx}', domain='plumber.example')
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
                    technical_issue_count=10,
                    normalization_version='analytics-v1',
                    deterministic_hash=f'h-a-{idx}',
                ),
                CampaignDailyMetric(
                    organization_id=org.id,
                    campaign_id=campaign.id,
                    metric_date=date(2026, 3, 5),
                    sessions=120,
                    technical_issue_count=8,
                    normalization_version='analytics-v1',
                    deterministic_hash=f'h-b-{idx}',
                ),
                TemporalSignalSnapshot(
                    campaign_id=campaign.id,
                    signal_type=TemporalSignalType.CUSTOM,
                    metric_name='internal_link_ratio',
                    metric_value=0.35,
                    observed_at=datetime.now(UTC),
                    source='feature_store_v1',
                    confidence=1.0,
                    version_hash=f's-{idx}-1',
                ),
                TemporalSignalSnapshot(
                    campaign_id=campaign.id,
                    signal_type=TemporalSignalType.CUSTOM,
                    metric_name='ranking_velocity',
                    metric_value=0.15,
                    observed_at=datetime.now(UTC),
                    source='feature_store_v1',
                    confidence=1.0,
                    version_hash=f's-{idx}-2',
                ),
                TemporalSignalSnapshot(
                    campaign_id=campaign.id,
                    signal_type=TemporalSignalType.CUSTOM,
                    metric_name='technical_issue_density',
                    metric_value=0.1,
                    observed_at=datetime.now(UTC),
                    source='feature_store_v1',
                    confidence=1.0,
                    version_hash=f's-{idx}-3',
                ),
                TemporalSignalSnapshot(
                    campaign_id=campaign.id,
                    signal_type=TemporalSignalType.CUSTOM,
                    metric_name='content_growth_rate',
                    metric_value=0.12,
                    observed_at=datetime.now(UTC),
                    source='feature_store_v1',
                    confidence=1.0,
                    version_hash=f's-{idx}-4',
                ),
            ]
        )

        rec = StrategyRecommendation(
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            recommendation_type='policy::test::action',
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
                metric_after=12.0,
                delta=2.0,
            )
        )

    db_session.commit()

    rows = build_cohort_rows(db_session)
    assert len(rows) == 3
    assert all('cohort_definition' in row for row in rows)
    assert all('outcome_delta' in row for row in rows)

    profiles = aggregate_feature_profiles(rows)
    assert len(profiles) == 1
    assert profiles[0]['support_count'] == 3
    assert profiles[0]['avg_internal_link_ratio'] > 0
