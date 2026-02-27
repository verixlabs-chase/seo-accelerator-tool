from __future__ import annotations

import json
import re
from datetime import UTC, datetime

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


def test_automation_export_deterministic_shape(client, db_session) -> None:
    token, _tenant_id = _login(client, 'a@example.com', 'pass-a')
    campaign = _create_campaign(client, token, 'Export Campaign', 'export.example')

    db_session.add(
        StrategyAutomationEvent(
            campaign_id=campaign['id'],
            evaluation_date=datetime(2026, 2, 1, tzinfo=UTC),
            prior_phase='stabilization',
            new_phase='growth',
            triggered_rules=json.dumps(['sustained_positive_slope']),
            momentum_snapshot=json.dumps({'momentum_score': 0.2}),
            action_summary=json.dumps({'status': 'evaluated'}),
            decision_hash='a' * 64,
            version_hash='v1',
        )
    )
    db_session.add(
        StrategyAutomationEvent(
            campaign_id=campaign['id'],
            evaluation_date=datetime(2026, 3, 1, tzinfo=UTC),
            prior_phase='growth',
            new_phase='acceleration',
            triggered_rules=json.dumps(['dominance_threshold_reached']),
            momentum_snapshot=json.dumps({'momentum_score': 0.6}),
            action_summary=json.dumps({'status': 'evaluated'}),
            decision_hash='b' * 64,
            version_hash='v1',
        )
    )
    db_session.commit()

    response = client.get(
        f"/api/v1/automation/campaign/{campaign['id']}/export",
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == 200
    payload = response.json()['data']

    assert payload['campaign_id'] == campaign['id']
    assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$', payload['export_generated_at'])
    assert [item['decision_hash'] for item in payload['events']] == ['a' * 64, 'b' * 64]
