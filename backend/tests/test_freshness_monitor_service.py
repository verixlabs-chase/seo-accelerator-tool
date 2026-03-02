from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.models.analytics_daily_metric import AnalyticsDailyMetric
from app.models.campaign import Campaign
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.models.user import User
from app.services import freshness_monitor_service


def _active_campaign(db_session):
    user = db_session.query(User).filter(User.email == "a@example.com").first()
    assert user is not None
    campaign = Campaign(
        id=str(uuid.uuid4()),
        tenant_id=user.tenant_id,
        organization_id=user.tenant_id,
        name='Freshness Campaign',
        domain='freshness.example',
        setup_state='Active',
        created_at=datetime.now(UTC),
    )
    db_session.add(campaign)
    db_session.commit()
    return campaign


def _seed_metric_rows(db_session, campaign: Campaign, metric_date: date) -> None:
    db_session.add(
        SearchConsoleDailyMetric(
            organization_id=campaign.organization_id,
            campaign_id=campaign.id,
            metric_date=metric_date,
            clicks=10,
            impressions=100,
            avg_position=2.5,
            deterministic_hash='sc-hash',
        )
    )
    db_session.add(
        AnalyticsDailyMetric(
            organization_id=campaign.organization_id,
            campaign_id=campaign.id,
            metric_date=metric_date,
            sessions=20,
            conversions=3,
            deterministic_hash='ga-hash',
        )
    )
    db_session.add(
        CampaignDailyMetric(
            organization_id=campaign.organization_id,
            campaign_id=campaign.id,
            metric_date=metric_date,
            clicks=10,
            impressions=100,
            avg_position=2.5,
            sessions=20,
            conversions=3,
            technical_issue_count=0,
            intelligence_score=90.0,
            reviews_last_30d=5,
            avg_rating_last_30d=4.5,
            deterministic_hash='cdm-hash',
        )
    )
    db_session.commit()


def test_fresh_campaign_returns_healthy(db_session, monkeypatch) -> None:
    settings = freshness_monitor_service.get_settings()
    monkeypatch.setattr(settings, 'traffic_fact_max_staleness_days', 2, raising=False)
    campaign = _active_campaign(db_session)
    evaluation_time = datetime(2026, 3, 2, tzinfo=UTC)
    _seed_metric_rows(db_session, campaign, evaluation_time.date())

    result = freshness_monitor_service.get_data_freshness_summary(db_session, evaluated_at=evaluation_time)

    assert result['status'] == 'healthy'
    assert result['stale_campaign_count'] == 0
    assert result['max_staleness_days'] == 0


def test_one_day_stale_returns_degraded(db_session, monkeypatch) -> None:
    settings = freshness_monitor_service.get_settings()
    monkeypatch.setattr(settings, 'traffic_fact_max_staleness_days', 2, raising=False)
    campaign = _active_campaign(db_session)
    evaluation_time = datetime(2026, 3, 2, tzinfo=UTC)
    _seed_metric_rows(db_session, campaign, evaluation_time.date() - timedelta(days=1))

    result = freshness_monitor_service.get_data_freshness_summary(db_session, evaluated_at=evaluation_time)

    assert result['status'] == 'degraded'
    assert result['stale_campaign_count'] == 0
    assert result['max_staleness_days'] == 1


def test_above_threshold_returns_stale(db_session, monkeypatch) -> None:
    settings = freshness_monitor_service.get_settings()
    monkeypatch.setattr(settings, 'traffic_fact_max_staleness_days', 2, raising=False)
    campaign = _active_campaign(db_session)
    evaluation_time = datetime(2026, 3, 5, tzinfo=UTC)
    _seed_metric_rows(db_session, campaign, evaluation_time.date() - timedelta(days=3))

    result = freshness_monitor_service.get_data_freshness_summary(db_session, evaluated_at=evaluation_time)

    assert result['status'] == 'stale'
    assert result['stale_campaign_count'] == 1
    assert result['max_staleness_days'] == 3


def test_replay_mode_does_not_break_check(db_session, monkeypatch) -> None:
    monkeypatch.setenv('REPLAY_MODE', '1')
    settings = freshness_monitor_service.get_settings()
    monkeypatch.setattr(settings, 'traffic_fact_max_staleness_days', 2, raising=False)
    campaign = _active_campaign(db_session)
    evaluation_time = datetime(2026, 3, 2, tzinfo=UTC)
    _seed_metric_rows(db_session, campaign, evaluation_time.date())

    result = freshness_monitor_service.get_data_freshness_summary(db_session, evaluated_at=evaluation_time)

    assert result['status'] == 'healthy'
    assert result['stale_campaign_count'] == 0
