from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.intelligence.feature_store import compute_features
from app.models.content import ContentAsset
from app.models.crawl import CrawlPageResult, TechnicalIssue
from app.models.temporal import MomentumMetric, TemporalSignalSnapshot, TemporalSignalType
from tests.conftest import create_test_campaign


def test_compute_features_returns_expected_keys_and_persists(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Feature Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Feature Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Feature Campaign',
        domain='feature.example',
    )

    db_session.add(
        ContentAsset(
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            cluster_name='Core',
            title='Published Asset',
            status='published',
            planned_month=1,
        )
    )

    db_session.add(
        CrawlPageResult(
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            crawl_run_id='run-1',
            page_id='page-1',
            status_code=200,
            is_indexable=1,
            title='Page 1',
        )
    )

    db_session.add(
        TechnicalIssue(
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            crawl_run_id='run-1',
            page_id=None,
            issue_code='no_internal_links',
            severity='low',
            details_json='{}',
        )
    )

    db_session.add(
        TemporalSignalSnapshot(
            campaign_id=campaign.id,
            signal_type=TemporalSignalType.CONTENT,
            metric_name='content_count',
            metric_value=2.0,
            observed_at=datetime.now(UTC) - timedelta(days=31),
            source='seed',
            confidence=1.0,
            version_hash='v1',
        )
    )

    db_session.add(
        MomentumMetric(
            campaign_id=campaign.id,
            metric_name='rank_avg_position_momentum',
            slope=-0.2,
            acceleration=0.0,
            volatility=0.1,
            window_days=30,
            computed_at=datetime.now(UTC),
            deterministic_hash='m1',
            profile_version='p1',
        )
    )

    db_session.commit()

    features = compute_features(campaign.id, db=db_session, persist=True)

    assert 'technical_issue_density' in features
    assert 'internal_link_ratio' in features
    assert 'ranking_velocity' in features
    assert 'content_growth_rate' in features

    persisted = (
        db_session.query(TemporalSignalSnapshot)
        .filter(TemporalSignalSnapshot.campaign_id == campaign.id, TemporalSignalSnapshot.source == 'feature_store_v1')
        .count()
    )
    assert persisted >= 4
