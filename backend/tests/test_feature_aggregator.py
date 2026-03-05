from __future__ import annotations

from datetime import UTC, datetime

from app.intelligence.feature_aggregator import aggregate_features, build_cohort_profiles, describe_campaign_cohort
from app.models.content import ContentAsset
from app.models.crawl import CrawlPageResult
from app.models.rank import CampaignKeyword, KeywordCluster
from app.models.temporal import TemporalSignalSnapshot, TemporalSignalType
from tests.conftest import create_test_campaign, create_test_crawl_run


def test_feature_aggregator_builds_cohort_rows_and_profiles(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Aggregator Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Aggregator Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Campaign 1',
        domain='plumber-alpha.example',
    )
    crawl_run_id = create_test_crawl_run(db_session, campaign.id, tenant.id)

    db_session.add_all(
        [
            CrawlPageResult(
                tenant_id=tenant.id,
                campaign_id=campaign.id,
                crawl_run_id=crawl_run_id,
                page_id='page-1',
                status_code=200,
                is_indexable=1,
                title='P1',
            ),
            ContentAsset(
                tenant_id=tenant.id,
                campaign_id=campaign.id,
                cluster_name='Core',
                title='Article 1',
                status='published',
                planned_month=1,
            ),
        ]
    )

    cluster = KeywordCluster(tenant_id=tenant.id, campaign_id=campaign.id, name='Core')
    db_session.add(cluster)
    db_session.flush()
    db_session.add(
        CampaignKeyword(
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            cluster_id=cluster.id,
            keyword='plumber in dallas',
            location_code='US',
        )
    )

    observed_at = datetime.now(UTC)
    db_session.add_all(
        [
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='internal_link_ratio',
                metric_value=0.72,
                observed_at=observed_at,
                source='feature_store_v1',
                confidence=1.0,
                version_hash='h1',
            ),
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='ranking_velocity',
                metric_value=-0.05,
                observed_at=observed_at,
                source='feature_store_v1',
                confidence=1.0,
                version_hash='h2',
            ),
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='technical_issue_density',
                metric_value=0.2,
                observed_at=observed_at,
                source='feature_store_v1',
                confidence=1.0,
                version_hash='h3',
            ),
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='content_growth_rate',
                metric_value=0.1,
                observed_at=observed_at,
                source='feature_store_v1',
                confidence=1.0,
                version_hash='h4',
            ),
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='crawl_health_score',
                metric_value=0.8,
                observed_at=observed_at,
                source='feature_store_v1',
                confidence=1.0,
                version_hash='h5',
            ),
        ]
    )
    db_session.commit()

    cohort_context = describe_campaign_cohort(db_session, campaign.id)
    assert cohort_context['cohort'].startswith('home_services')

    rows = aggregate_features(db_session)
    assert rows
    assert rows[0]['campaign_count'] >= 1

    profiles = build_cohort_profiles(db_session)
    assert cohort_context['cohort'] in profiles
    assert 'internal_link_ratio_threshold' in profiles[cohort_context['cohort']]
