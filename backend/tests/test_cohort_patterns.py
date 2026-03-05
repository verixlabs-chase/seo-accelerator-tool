from __future__ import annotations

from datetime import UTC, datetime

from app.intelligence.pattern_engine import discover_cohort_patterns
from app.models.content import ContentAsset
from app.models.crawl import CrawlPageResult
from app.models.rank import CampaignKeyword, KeywordCluster
from app.models.temporal import TemporalSignalSnapshot, TemporalSignalType
from tests.conftest import create_test_campaign, create_test_crawl_run, create_test_page


def test_discover_cohort_patterns_detects_internal_link_deficit(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Cohort Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Cohort Org')
    healthy = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Healthy Campaign',
        domain='plumber-healthy.example',
    )
    weak = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Weak Campaign',
        domain='plumber-weak.example',
    )

    for campaign in (healthy, weak):
        campaign_crawl_run_id = create_test_crawl_run(db_session, campaign.id, tenant.id)
        page_id = create_test_page(db_session, tenant.id, campaign.id)
        db_session.add(
            CrawlPageResult(
                tenant_id=tenant.id,
                campaign_id=campaign.id,
                crawl_run_id=campaign_crawl_run_id,
                page_id=page_id,
                status_code=200,
                is_indexable=1,
                title='Page',
            )
        )
        db_session.add(
            ContentAsset(
                tenant_id=tenant.id,
                campaign_id=campaign.id,
                cluster_name='Core',
                title='Published',
                status='published',
                planned_month=1,
            )
        )
        cluster = KeywordCluster(tenant_id=tenant.id, campaign_id=campaign.id, name='Core')
        db_session.add(cluster)
        db_session.flush()
        db_session.add(
            CampaignKeyword(
                tenant_id=tenant.id,
                campaign_id=campaign.id,
                cluster_id=cluster.id,
                keyword='plumber in usa',
                location_code='US',
            )
        )

    observed_at = datetime.now(UTC)
    db_session.add_all(
        [
            TemporalSignalSnapshot(
                campaign_id=healthy.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='internal_link_ratio',
                metric_value=0.82,
                observed_at=observed_at,
                source='feature_store_v1',
                confidence=1.0,
                version_hash='c1',
            ),
            TemporalSignalSnapshot(
                campaign_id=healthy.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='ranking_velocity',
                metric_value=-0.02,
                observed_at=observed_at,
                source='feature_store_v1',
                confidence=1.0,
                version_hash='c2',
            ),
            TemporalSignalSnapshot(
                campaign_id=healthy.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='content_growth_rate',
                metric_value=0.05,
                observed_at=observed_at,
                source='feature_store_v1',
                confidence=1.0,
                version_hash='c3',
            ),
            TemporalSignalSnapshot(
                campaign_id=weak.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='internal_link_ratio',
                metric_value=0.3,
                observed_at=observed_at,
                source='feature_store_v1',
                confidence=1.0,
                version_hash='c4',
            ),
            TemporalSignalSnapshot(
                campaign_id=weak.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='ranking_velocity',
                metric_value=-0.1,
                observed_at=observed_at,
                source='feature_store_v1',
                confidence=1.0,
                version_hash='c5',
            ),
            TemporalSignalSnapshot(
                campaign_id=weak.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='content_growth_rate',
                metric_value=-0.1,
                observed_at=observed_at,
                source='feature_store_v1',
                confidence=1.0,
                version_hash='c6',
            ),
        ]
    )
    db_session.commit()

    patterns = discover_cohort_patterns(
        db_session,
        campaign_id=weak.id,
        features={
            'internal_link_ratio': 0.3,
            'ranking_velocity': -0.1,
            'content_growth_rate': -0.1,
        },
    )

    keys = {item['pattern_key'] for item in patterns}
    assert 'internal_link_deficit' in keys
