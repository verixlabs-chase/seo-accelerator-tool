from __future__ import annotations

from datetime import date

from app.intelligence.signal_assembler import assemble_signals
from app.models.campaign import Campaign
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.content import ContentAsset
from app.models.crawl import TechnicalIssue
from app.models.local import LocalHealthSnapshot, LocalProfile
from app.models.rank import CampaignKeyword, KeywordCluster, Ranking
from app.models.tenant import Tenant


def test_assemble_signals_collects_expected_fields(db_session) -> None:
    tenant = Tenant(name='Assembler Tenant', status='Active')
    db_session.add(tenant)
    db_session.flush()

    campaign = Campaign(tenant_id=tenant.id, name='Assembler Campaign', domain='assembler.example')
    db_session.add(campaign)
    db_session.flush()

    profile = LocalProfile(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        provider='gbp',
        profile_name='Assembler Profile',
        map_pack_position=4,
    )
    db_session.add(profile)
    db_session.flush()

    db_session.add(
        LocalHealthSnapshot(
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            profile_id=profile.id,
            health_score=81.0,
            details_json='{}',
        )
    )

    cluster = KeywordCluster(tenant_id=tenant.id, campaign_id=campaign.id, name='Core')
    db_session.add(cluster)
    db_session.flush()

    kw = CampaignKeyword(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        cluster_id=cluster.id,
        keyword='best plumber',
        location_code='US',
    )
    db_session.add(kw)
    db_session.flush()

    db_session.add(Ranking(tenant_id=tenant.id, campaign_id=campaign.id, keyword_id=kw.id, current_position=8, delta=2))
    db_session.add(Ranking(tenant_id=tenant.id, campaign_id=campaign.id, keyword_id=kw.id, current_position=10, delta=4))

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
        TechnicalIssue(
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            crawl_run_id='run-1',
            page_id=None,
            issue_code='missing_title',
            severity='high',
            details_json='{}',
        )
    )

    db_session.add(
        CampaignDailyMetric(
            organization_id=tenant.id,
            portfolio_id=None,
            sub_account_id=None,
            campaign_id=campaign.id,
            metric_date=date(2026, 3, 5),
            clicks=40,
            impressions=200,
            avg_position=9.0,
            sessions=120,
            conversions=12,
            technical_issue_count=1,
            intelligence_score=55.0,
            reviews_last_30d=3,
            avg_rating_last_30d=4.4,
            normalization_version='analytics-v1',
            deterministic_hash='hash-metric',
        )
    )

    db_session.commit()

    payload = assemble_signals(campaign.id, db=db_session)

    assert payload['technical_issue_count'] == 1.0
    assert round(payload['avg_rank'], 2) == 9.0
    assert payload['content_count'] == 1.0
    assert round(payload['local_health'], 2) == 0.81
    assert payload['clicks'] == 40.0
    assert payload['impressions'] == 200.0
    assert round(payload['ctr'], 3) == 0.2
