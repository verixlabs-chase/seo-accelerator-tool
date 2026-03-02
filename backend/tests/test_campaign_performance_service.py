from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.campaign import Campaign
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.organization import Organization
from app.services import campaign_performance_service


def _organization_id(db_session) -> str:
    return db_session.query(Organization.id).order_by(Organization.created_at.asc(), Organization.id.asc()).first()[0]


def test_performance_summary_uses_campaign_daily_metrics_when_window_is_present(db_session, monkeypatch) -> None:
    organization_id = _organization_id(db_session)
    campaign = Campaign(
        tenant_id=organization_id,
        organization_id=organization_id,
        name='Performance Campaign',
        domain=f'{uuid.uuid4().hex}.example',
        created_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
    )
    db_session.add(campaign)
    db_session.flush()

    now = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)
    db_session.add_all(
        [
            CampaignDailyMetric(
                organization_id=organization_id,
                portfolio_id=None,
                sub_account_id=None,
                campaign_id=campaign.id,
                metric_date=datetime(2026, 3, 1, tzinfo=UTC).date(),
                clicks=None,
                impressions=None,
                avg_position=8.0,
                sessions=None,
                conversions=None,
                technical_issue_count=1,
                intelligence_score=77.0,
                reviews_last_30d=5,
                avg_rating_last_30d=4.5,
                cost=None,
                revenue=None,
                normalization_version='analytics-v1',
                deterministic_hash='a' * 64,
                created_at=now,
                updated_at=now,
            ),
            CampaignDailyMetric(
                organization_id=organization_id,
                portfolio_id=None,
                sub_account_id=None,
                campaign_id=campaign.id,
                metric_date=datetime(2026, 3, 2, tzinfo=UTC).date(),
                clicks=None,
                impressions=None,
                avg_position=6.0,
                sessions=None,
                conversions=None,
                technical_issue_count=0,
                intelligence_score=79.0,
                reviews_last_30d=6,
                avg_rating_last_30d=4.6,
                cost=None,
                revenue=None,
                normalization_version='analytics-v1',
                deterministic_hash='b' * 64,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()

    def _fail(*_args, **_kwargs):
        raise AssertionError('live provider fallback should not be used when campaign_daily_metrics rows exist')

    monkeypatch.setattr(campaign_performance_service, 'resolve_provider_credentials', _fail)

    summary = campaign_performance_service.build_campaign_performance_summary(
        db_session,
        campaign=campaign,
        date_from=datetime(2026, 3, 2, 0, 0, tzinfo=UTC),
        date_to=datetime(2026, 3, 2, 23, 59, tzinfo=UTC),
    )

    assert summary['campaign_id'] == campaign.id
    assert summary['clicks'] == 0.0
    assert summary['impressions'] == 0.0
    assert summary['sessions'] == 0.0
    assert summary['conversions'] == 0.0
    assert summary['avg_position'] == 6.0
