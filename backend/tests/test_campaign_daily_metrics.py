import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.analytics_daily_metric import AnalyticsDailyMetric
from app.models.campaign import Campaign
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.crawl import CrawlRun, TechnicalIssue
from app.models.intelligence import IntelligenceScore
from app.models.local import LocalProfile, ReviewVelocitySnapshot
from app.models.organization import Organization
from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.models.tenant import Tenant
from app.services import analytics_service


def _organization_id(db_session) -> str:
    return db_session.query(Organization.id).order_by(Organization.created_at.asc(), Organization.id.asc()).first()[0]


def _build_campaign(db_session, *, organization_id: str | None) -> Campaign:
    tenant_id = organization_id or str(uuid.uuid4())
    tenant = db_session.query(Tenant).filter(Tenant.id == tenant_id).one_or_none()
    if tenant is None:
        tenant = Tenant(
            id=tenant_id,
            name=f"Analytics Tenant {tenant_id[:8]}",
            status="Active",
            created_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
        )
        db_session.add(tenant)
        db_session.flush()

    campaign = Campaign(
        tenant_id=tenant.id,
        organization_id=organization_id,
        name='Analytics Campaign',
        domain=f'{uuid.uuid4().hex}.example',
        created_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
    )
    db_session.add(campaign)
    db_session.flush()
    return campaign

def test_campaign_daily_metric_hash_is_stable() -> None:
    metric_input = analytics_service.CampaignDailyMetricInput(
        organization_id='org-1',
        portfolio_id='portfolio-1',
        sub_account_id='sub-1',
        campaign_id='campaign-1',
        metric_date=date(2026, 3, 1),
        clicks=12,
        impressions=345,
        avg_position=4.5,
        sessions=23,
        conversions=3,
        technical_issue_count=2,
        intelligence_score=81.2,
        reviews_last_30d=9,
        avg_rating_last_30d=4.7,
        cost=Decimal('10.50'),
        revenue=Decimal('55.00'),
    )

    first = analytics_service.normalize_campaign_daily_metric(metric_input)
    second = analytics_service.normalize_campaign_daily_metric(metric_input)

    assert first['deterministic_hash'] == second['deterministic_hash']
    assert first == second


def test_campaign_daily_metric_rollup_is_idempotent(db_session) -> None:
    organization_id = _organization_id(db_session)
    campaign = _build_campaign(db_session, organization_id=organization_id)
    metric_date = date(2026, 3, 1)
    captured_at = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

    db_session.add(
        SearchConsoleDailyMetric(
            organization_id=organization_id,
            campaign_id=campaign.id,
            metric_date=metric_date,
            clicks=12,
            impressions=300,
            avg_position=7.0,
            deterministic_hash='s' * 64,
            created_at=captured_at,
            updated_at=captured_at,
        )
    )
    db_session.add(
        AnalyticsDailyMetric(
            organization_id=organization_id,
            campaign_id=campaign.id,
            metric_date=metric_date,
            sessions=23,
            conversions=3,
            deterministic_hash='a' * 64,
            created_at=captured_at,
            updated_at=captured_at,
        )
    )
    crawl_run = CrawlRun(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        crawl_type='deep',
        status='complete',
        seed_url='https://example.com',
        created_at=captured_at,
        started_at=captured_at,
        finished_at=captured_at,
    )
    db_session.add(crawl_run)
    db_session.flush()
    db_session.add(
        TechnicalIssue(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            crawl_run_id=crawl_run.id,
            page_id=None,
            issue_code='missing_title',
            severity='high',
            detected_at=captured_at,
        )
    )
    db_session.add(
        IntelligenceScore(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            score_type='composite',
            score_value=88.5,
            captured_at=captured_at,
        )
    )
    profile = LocalProfile(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        provider='gbp',
        profile_name='Primary',
        created_at=captured_at,
        updated_at=captured_at,
    )
    db_session.add(profile)
    db_session.flush()
    db_session.add(
        ReviewVelocitySnapshot(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            profile_id=profile.id,
            reviews_last_30d=11,
            avg_rating_last_30d=4.6,
            captured_at=captured_at,
        )
    )
    db_session.commit()

    first = analytics_service.rollup_campaign_daily_metrics_for_date(db=db_session, metric_date=metric_date)
    row = db_session.query(CampaignDailyMetric).filter(CampaignDailyMetric.campaign_id == campaign.id).one()
    first_updated_at = row.updated_at
    first_hash = row.deterministic_hash

    second = analytics_service.rollup_campaign_daily_metrics_for_date(db=db_session, metric_date=metric_date)
    rows = db_session.query(CampaignDailyMetric).filter(CampaignDailyMetric.campaign_id == campaign.id).all()

    assert first.inserted_rows == 1
    assert first.updated_rows == 0
    assert first.skipped_rows == 0
    assert second.inserted_rows == 0
    assert second.updated_rows == 0
    assert second.skipped_rows == 1
    assert len(rows) == 1
    assert rows[0].deterministic_hash == first_hash
    assert rows[0].updated_at == first_updated_at
    assert rows[0].organization_id == organization_id
    assert rows[0].clicks == 12
    assert rows[0].impressions == 300
    assert rows[0].avg_position == pytest.approx(7.0)
    assert rows[0].sessions == 23
    assert rows[0].conversions == 3
    assert rows[0].technical_issue_count == 1
    assert rows[0].reviews_last_30d == 11


def test_campaign_daily_metric_unique_constraint_enforced(db_session) -> None:
    organization_id = _organization_id(db_session)
    campaign = _build_campaign(db_session, organization_id=organization_id)
    metric_date = date(2026, 3, 1)
    now = datetime.now(UTC)

    db_session.add(
        CampaignDailyMetric(
            organization_id=organization_id,
            portfolio_id=None,
            sub_account_id=None,
            campaign_id=campaign.id,
            metric_date=metric_date,
            technical_issue_count=0,
            reviews_last_30d=0,
            normalization_version='analytics-v1',
            deterministic_hash='a' * 64,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()

    db_session.add(
        CampaignDailyMetric(
            organization_id=organization_id,
            portfolio_id=None,
            sub_account_id=None,
            campaign_id=campaign.id,
            metric_date=metric_date,
            technical_issue_count=0,
            reviews_last_30d=0,
            normalization_version='analytics-v1',
            deterministic_hash='b' * 64,
            created_at=now,
            updated_at=now,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_campaign_daily_metric_rollup_requires_organization_scope(db_session) -> None:
    campaign = _build_campaign(db_session, organization_id=None)
    db_session.commit()

    with pytest.raises(ValueError, match='organization_id'):
        analytics_service.rollup_campaign_daily_metrics_for_date(db=db_session, metric_date=date(2026, 3, 1))

    assert db_session.query(CampaignDailyMetric).filter(CampaignDailyMetric.campaign_id == campaign.id).count() == 0


def test_campaign_daily_metric_source_inventory_matches_current_storage() -> None:
    inventory = analytics_service.get_campaign_daily_metric_source_inventory()

    assert inventory['clicks'] == {
        'table': 'search_console_daily_metrics',
        'column': 'clicks',
        'timestamp_column': 'metric_date',
    }
    assert inventory['impressions'] == {
        'table': 'search_console_daily_metrics',
        'column': 'impressions',
        'timestamp_column': 'metric_date',
    }
    assert inventory['avg_position'] == {
        'table': 'search_console_daily_metrics',
        'column': 'avg_position',
        'timestamp_column': 'metric_date',
    }
    assert inventory['sessions'] == {
        'table': 'analytics_daily_metrics',
        'column': 'sessions',
        'timestamp_column': 'metric_date',
    }
    assert inventory['conversions'] == {
        'table': 'analytics_daily_metrics',
        'column': 'conversions',
        'timestamp_column': 'metric_date',
    }


def test_campaign_daily_metric_range_rollup_is_idempotent(db_session) -> None:
    organization_id = _organization_id(db_session)
    campaign = _build_campaign(db_session, organization_id=organization_id)
    day_one = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    day_two = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)

    db_session.add_all(
        [
            SearchConsoleDailyMetric(
                organization_id=organization_id,
                campaign_id=campaign.id,
                metric_date=day_one.date(),
                clicks=10,
                impressions=200,
                avg_position=6.0,
                deterministic_hash='1' * 64,
                created_at=day_one,
                updated_at=day_one,
            ),
            SearchConsoleDailyMetric(
                organization_id=organization_id,
                campaign_id=campaign.id,
                metric_date=day_two.date(),
                clicks=14,
                impressions=240,
                avg_position=4.0,
                deterministic_hash='2' * 64,
                created_at=day_two,
                updated_at=day_two,
            ),
            AnalyticsDailyMetric(
                organization_id=organization_id,
                campaign_id=campaign.id,
                metric_date=day_one.date(),
                sessions=20,
                conversions=2,
                deterministic_hash='3' * 64,
                created_at=day_one,
                updated_at=day_one,
            ),
            AnalyticsDailyMetric(
                organization_id=organization_id,
                campaign_id=campaign.id,
                metric_date=day_two.date(),
                sessions=25,
                conversions=4,
                deterministic_hash='4' * 64,
                created_at=day_two,
                updated_at=day_two,
            ),
        ]
    )
    crawl_run = CrawlRun(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        crawl_type='deep',
        status='complete',
        seed_url='https://example.com',
        created_at=day_one,
        started_at=day_one,
        finished_at=day_two,
    )
    db_session.add(crawl_run)
    db_session.flush()
    db_session.add_all(
        [
            TechnicalIssue(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                crawl_run_id=crawl_run.id,
                page_id=None,
                issue_code='missing_title',
                severity='high',
                detected_at=day_one,
            ),
            TechnicalIssue(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                crawl_run_id=crawl_run.id,
                page_id=None,
                issue_code='missing_description',
                severity='medium',
                detected_at=day_two,
            ),
            IntelligenceScore(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                score_type='composite',
                score_value=80.0,
                captured_at=day_one,
            ),
            IntelligenceScore(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                score_type='composite',
                score_value=84.0,
                captured_at=day_two,
            ),
        ]
    )
    profile = LocalProfile(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        provider='gbp',
        profile_name='Primary',
        created_at=day_one,
        updated_at=day_two,
    )
    db_session.add(profile)
    db_session.flush()
    db_session.add_all(
        [
            ReviewVelocitySnapshot(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                profile_id=profile.id,
                reviews_last_30d=9,
                avg_rating_last_30d=4.3,
                captured_at=day_one,
            ),
            ReviewVelocitySnapshot(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                profile_id=profile.id,
                reviews_last_30d=12,
                avg_rating_last_30d=4.4,
                captured_at=day_two,
            ),
        ]
    )
    db_session.commit()

    first = analytics_service.rollup_campaign_daily_metrics_for_range(
        db=db_session,
        date_from='2026-03-01',
        date_to='2026-03-02',
    )
    second = analytics_service.rollup_campaign_daily_metrics_for_range(
        db=db_session,
        date_from='2026-03-01',
        date_to='2026-03-02',
    )
    rows = (
        db_session.query(CampaignDailyMetric)
        .filter(CampaignDailyMetric.campaign_id == campaign.id)
        .order_by(CampaignDailyMetric.metric_date.asc())
        .all()
    )

    assert first.days_processed == 2
    assert first.inserted_rows == 2
    assert first.updated_rows == 0
    assert second.inserted_rows == 0
    assert second.updated_rows == 0
    assert second.skipped_rows == 2
    assert len(rows) == 2
    assert [row.metric_date.isoformat() for row in rows] == ['2026-03-01', '2026-03-02']
    assert rows[0].clicks == 10
    assert rows[1].sessions == 25







