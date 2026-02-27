from __future__ import annotations

import json
from datetime import UTC, datetime

from app.models.campaign import Campaign
from app.models.strategy_automation_event import StrategyAutomationEvent


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post('/api/v1/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200
    payload = response.json()['data']
    return payload['access_token'], payload['user']['tenant_id']


def _create_campaign(client, token: str, name: str, domain: str) -> dict:
    response = client.post(
        '/api/v1/campaigns',
        json={'name': name, 'domain': domain},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == 200
    return response.json()['data']


def test_automation_timeline_returns_sorted_events(client, db_session) -> None:
    token, _tenant_id = _login(client, 'a@example.com', 'pass-a')
    campaign = _create_campaign(client, token, 'Timeline Campaign', 'timeline.example')

    db_session.add(
        StrategyAutomationEvent(
            campaign_id=campaign['id'],
            evaluation_date=datetime(2026, 3, 1, tzinfo=UTC),
            prior_phase='stabilization',
            new_phase='growth',
            triggered_rules=json.dumps(['sustained_positive_slope']),
            momentum_snapshot=json.dumps({'momentum_score': 0.2}),
            action_summary=json.dumps({'status': 'evaluated'}),
            decision_hash='b' * 64,
            version_hash='v1',
        )
    )
    db_session.add(
        StrategyAutomationEvent(
            campaign_id=campaign['id'],
            evaluation_date=datetime(2026, 2, 1, tzinfo=UTC),
            prior_phase='recovery',
            new_phase='stabilization',
            triggered_rules=json.dumps(['default_stabilization_band']),
            momentum_snapshot=json.dumps({'momentum_score': 0.05}),
            action_summary=json.dumps({'status': 'evaluated'}),
            decision_hash='a' * 64,
            version_hash='v1',
        )
    )
    db_session.commit()

    response = client.get(
        f"/api/v1/automation/campaign/{campaign['id']}/timeline",
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == 200
    items = response.json()['data']['items']
    assert len(items) == 2
    assert items[0]['evaluation_date'] < items[1]['evaluation_date']
    assert items[0]['decision_hash'] == 'a' * 64
    assert items[1]['decision_hash'] == 'b' * 64


def test_automation_timeline_tenant_scoped(client, db_session) -> None:
    token_a, tenant_a = _login(client, 'a@example.com', 'pass-a')
    token_b, _tenant_b = _login(client, 'b@example.com', 'pass-b')
    campaign = Campaign(tenant_id=tenant_a, name='Scoped', domain='scoped.example')
    db_session.add(campaign)
    db_session.commit()

    response = client.get(
        f'/api/v1/automation/campaign/{campaign.id}/timeline',
        headers={'Authorization': f'Bearer {token_b}'},
    )
    assert response.status_code == 404
