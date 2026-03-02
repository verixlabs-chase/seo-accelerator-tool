from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.analytics_daily_metric import AnalyticsDailyMetric
from app.models.campaign import Campaign
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.models.user import User
from app.services.operational_telemetry_service import (
    record_provider_call,
    record_replay_execution,
)


def _login(client, email: str, password: str) -> str:
    response = client.post('/api/v1/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200
    return response.json()['data']['access_token']


def _seed_fresh_campaign(db_session) -> None:
    user = db_session.query(User).filter(User.email == 'a@example.com').first()
    assert user is not None
    campaign = Campaign(
        id=str(uuid.uuid4()),
        tenant_id=user.tenant_id,
        organization_id=user.tenant_id,
        name='Fresh Data Campaign',
        domain='fresh-data.example',
        setup_state='Active',
        created_at=datetime.now(UTC),
    )
    db_session.add(campaign)
    db_session.commit()
    today = datetime.now(UTC).date()
    db_session.add(
        SearchConsoleDailyMetric(
            organization_id=campaign.organization_id,
            campaign_id=campaign.id,
            metric_date=today,
            clicks=5,
            impressions=50,
            avg_position=3.2,
            deterministic_hash='sc',
        )
    )
    db_session.add(
        AnalyticsDailyMetric(
            organization_id=campaign.organization_id,
            campaign_id=campaign.id,
            metric_date=today,
            sessions=11,
            conversions=2,
            deterministic_hash='ga',
        )
    )
    db_session.add(
        CampaignDailyMetric(
            organization_id=campaign.organization_id,
            campaign_id=campaign.id,
            metric_date=today,
            clicks=5,
            impressions=50,
            avg_position=3.2,
            sessions=11,
            conversions=2,
            technical_issue_count=0,
            intelligence_score=88.0,
            reviews_last_30d=1,
            avg_rating_last_30d=5.0,
            deterministic_hash='cdm',
        )
    )
    db_session.commit()


def test_operational_health_requires_platform_role(client) -> None:
    token = _login(client, 'org-admin@example.com', 'pass-org-admin')

    response = client.get(
        '/api/v1/system/operational-health',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 403


def test_operational_health_returns_expected_shape(client, db_session) -> None:
    _seed_fresh_campaign(db_session)
    record_provider_call(provider='rank', duration_ms=120, success=True)
    record_provider_call(provider='rank', duration_ms=180, success=False)
    record_replay_execution(duration_ms=90, success=True, drift_detected=False)

    token = _login(client, 'platform-admin@example.com', 'pass-platform-admin')
    response = client.get(
        '/api/v1/system/operational-health',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 200
    payload = response.json()['data']['operational_health']
    assert 'recent_p95_latency_ms' in payload
    assert 'recent_p99_latency_ms' in payload
    assert 'queue_depth' in payload
    assert 'provider_error_bands' in payload
    assert 'replay' in payload
    assert 'slow_query_count' in payload
    assert 'slo_targets' in payload
    assert 'data_freshness' in payload
    assert payload['replay']['drift_status'] == 'clean'
    assert payload['provider_error_bands'][0]['provider'] == 'rank'
    assert payload['data_freshness']['status'] == 'healthy'


def test_system_data_freshness_returns_expected_shape(client, db_session) -> None:
    _seed_fresh_campaign(db_session)
    token = _login(client, 'platform-admin@example.com', 'pass-platform-admin')

    response = client.get(
        '/api/v1/system/data-freshness',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 200
    payload = response.json()['data']
    assert payload['status'] == 'healthy'
    assert payload['stale_campaign_count'] == 0
    assert payload['max_staleness_days'] == 0
    assert 'evaluated_at' in payload
