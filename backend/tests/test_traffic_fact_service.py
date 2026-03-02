from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.models.analytics_daily_metric import AnalyticsDailyMetric
from app.models.campaign import Campaign
from app.models.organization import Organization
from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.services import traffic_fact_service


def _organization_id(db_session) -> str:
    return db_session.query(Organization.id).order_by(Organization.created_at.asc(), Organization.id.asc()).first()[0]


def _campaign(db_session, organization_id: str) -> Campaign:
    campaign = Campaign(
        tenant_id=organization_id,
        organization_id=organization_id,
        name='Fact Campaign',
        domain='facts.example',
        created_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
    )
    db_session.add(campaign)
    db_session.flush()
    return campaign


def test_search_console_daily_metric_upsert_is_idempotent(db_session) -> None:
    organization_id = _organization_id(db_session)
    campaign = _campaign(db_session, organization_id)

    first = traffic_fact_service.upsert_search_console_daily_metric(
        db=db_session,
        metric_input=traffic_fact_service.SearchConsoleDailyMetricInput(
            organization_id=organization_id,
            campaign_id=campaign.id,
            metric_date=date(2026, 3, 1),
            clicks=12,
            impressions=300,
            avg_position=5.5,
        ),
    )
    db_session.commit()
    second = traffic_fact_service.upsert_search_console_daily_metric(
        db=db_session,
        metric_input=traffic_fact_service.SearchConsoleDailyMetricInput(
            organization_id=organization_id,
            campaign_id=campaign.id,
            metric_date=date(2026, 3, 1),
            clicks=12,
            impressions=300,
            avg_position=5.5,
        ),
    )

    row = db_session.query(SearchConsoleDailyMetric).filter(SearchConsoleDailyMetric.campaign_id == campaign.id).one()

    assert first.inserted is True
    assert second.skipped is True
    assert row.clicks == 12
    assert row.impressions == 300


def test_analytics_daily_metric_upsert_updates_on_hash_change(db_session) -> None:
    organization_id = _organization_id(db_session)
    campaign = _campaign(db_session, organization_id)

    traffic_fact_service.upsert_analytics_daily_metric(
        db=db_session,
        metric_input=traffic_fact_service.AnalyticsDailyMetricInput(
            organization_id=organization_id,
            campaign_id=campaign.id,
            metric_date=date(2026, 3, 1),
            sessions=20,
            conversions=2,
        ),
    )
    db_session.commit()
    outcome = traffic_fact_service.upsert_analytics_daily_metric(
        db=db_session,
        metric_input=traffic_fact_service.AnalyticsDailyMetricInput(
            organization_id=organization_id,
            campaign_id=campaign.id,
            metric_date=date(2026, 3, 1),
            sessions=25,
            conversions=4,
        ),
    )
    db_session.commit()

    row = db_session.query(AnalyticsDailyMetric).filter(AnalyticsDailyMetric.campaign_id == campaign.id).one()

    assert outcome.updated is True
    assert row.sessions == 25
    assert row.conversions == 4



def test_search_console_sync_only_fetches_missing_days_and_is_idempotent(db_session, monkeypatch) -> None:
    organization_id = _organization_id(db_session)
    campaign = _campaign(db_session, organization_id)

    monkeypatch.setattr(
        traffic_fact_service,
        'resolve_provider_credentials',
        lambda *_args, **_kwargs: {'search_console_site_url': 'sc-domain:facts.example', 'ga4_property_id': 'prop-1'},
    )

    calls: list[dict] = []

    class _SearchAdapter:
        def __init__(self, **_kwargs):
            pass

        def execute(self, request):
            calls.append(dict(request.payload))
            return SimpleNamespace(
                success=True,
                raw_payload={
                    'rows': [
                        {'keys': ['20260301'], 'clicks': 12, 'impressions': 300, 'position': 5.5},
                        {'keys': ['20260302'], 'clicks': 7, 'impressions': 150, 'position': 6.0},
                    ]
                },
            )

    monkeypatch.setattr(traffic_fact_service, 'SearchConsoleProviderAdapter', _SearchAdapter)

    first = traffic_fact_service.sync_search_console_daily_metrics_for_campaign(
        db=db_session,
        campaign=campaign,
        start_date='2026-03-01',
        end_date='2026-03-02',
    )
    second = traffic_fact_service.sync_search_console_daily_metrics_for_campaign(
        db=db_session,
        campaign=campaign,
        start_date='2026-03-01',
        end_date='2026-03-02',
    )

    rows = db_session.query(SearchConsoleDailyMetric).filter(SearchConsoleDailyMetric.campaign_id == campaign.id).all()

    assert first.provider_calls == 1
    assert first.inserted_rows == 2
    assert second.requested_days == 0
    assert second.provider_calls == 0
    assert len(calls) == 1
    assert len(rows) == 2


def test_analytics_sync_replay_mode_skips_provider_calls(db_session, monkeypatch) -> None:
    organization_id = _organization_id(db_session)
    campaign = _campaign(db_session, organization_id)

    monkeypatch.setenv('REPLAY_MODE', '1')

    class _AnalyticsAdapter:
        def __init__(self, **_kwargs):
            pass

        def execute(self, _request):
            raise AssertionError('provider call should be skipped in replay mode')

    monkeypatch.setattr(traffic_fact_service, 'GoogleAnalyticsProviderAdapter', _AnalyticsAdapter)

    result = traffic_fact_service.sync_analytics_daily_metrics_for_campaign(
        db=db_session,
        campaign=campaign,
        start_date='2026-03-01',
        end_date='2026-03-02',
    )

    assert result.replay_skipped is True
    assert result.provider_calls == 0
    assert db_session.query(AnalyticsDailyMetric).filter(AnalyticsDailyMetric.campaign_id == campaign.id).count() == 0
