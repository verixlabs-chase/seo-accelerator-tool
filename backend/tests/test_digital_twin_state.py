from datetime import UTC, datetime

from app.intelligence.digital_twin.twin_state_model import DigitalTwinState
from app.models.content import ContentAsset
from app.models.crawl import CrawlPageResult, TechnicalIssue
from app.models.local import LocalHealthSnapshot, LocalProfile
from app.models.rank import CampaignKeyword, KeywordCluster, Ranking
from app.models.temporal import MomentumMetric
from tests.conftest import create_test_campaign, create_test_crawl_run, create_test_page


def test_digital_twin_state_from_campaign_data(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Twin Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Twin Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Twin Campaign',
        domain='twin.example',
    )
    crawl_run_id = create_test_crawl_run(db_session, campaign.id, tenant.id)
    page_id = create_test_page(db_session, tenant.id, campaign.id)

    profile = LocalProfile(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        provider='gbp',
        profile_name='Twin Profile',
    )
    db_session.add(profile)
    db_session.flush()

    db_session.add(
        LocalHealthSnapshot(
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            profile_id=profile.id,
            health_score=77.0,
            details_json='{}',
        )
    )

    cluster = KeywordCluster(tenant_id=tenant.id, campaign_id=campaign.id, name='Core')
    db_session.add(cluster)
    db_session.flush()

    keyword = CampaignKeyword(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        cluster_id=cluster.id,
        keyword='test keyword',
        location_code='US',
    )
    db_session.add(keyword)
    db_session.flush()

    db_session.add(Ranking(tenant_id=tenant.id, campaign_id=campaign.id, keyword_id=keyword.id, current_position=8, delta=1))
    db_session.add(Ranking(tenant_id=tenant.id, campaign_id=campaign.id, keyword_id=keyword.id, current_position=10, delta=2))

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
            crawl_run_id=crawl_run_id,
            page_id=page_id,
            status_code=200,
            is_indexable=1,
            title='Page 1',
        )
    )

    db_session.add(
        TechnicalIssue(
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            crawl_run_id=crawl_run_id,
            page_id=None,
            issue_code='missing_title',
            severity='high',
            details_json='{}',
        )
    )

    db_session.add(
        MomentumMetric(
            campaign_id=campaign.id,
            metric_name='rank_avg_position_momentum',
            slope=-0.25,
            acceleration=0.0,
            volatility=0.1,
            window_days=30,
            computed_at=datetime.now(UTC),
            deterministic_hash='twin-momentum',
            profile_version='v1',
        )
    )

    db_session.commit()

    state = DigitalTwinState.from_campaign_data(db_session, campaign.id)

    assert state.campaign_id == campaign.id
    assert state.avg_rank == 9.0
    assert state.technical_issue_count == 1
    assert state.content_page_count == 1
    assert state.local_health_score == 0.77
    assert state.internal_link_count >= 0
