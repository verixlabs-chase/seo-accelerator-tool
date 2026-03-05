from __future__ import annotations


def _login(client, email: str, password: str) -> str:
    response = client.post('/api/v1/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200
    return response.json()['data']['access_token']


def _create_campaign(client, token: str, name: str, domain: str) -> dict:
    response = client.post(
        '/api/v1/campaigns',
        json={'name': name, 'domain': domain},
        headers={'Authorization': 'Bearer ' + token},
    )
    assert response.status_code == 200
    return response.json()['data']


def test_intelligence_metrics_endpoints_return_contract(client) -> None:
    token = _login(client, 'org-admin@example.com', 'pass-org-admin')
    campaign = _create_campaign(client, token, 'Metrics API Campaign', 'metrics-api.example')

    campaign_resp = client.get(
        '/api/v1/intelligence/metrics/campaign/' + campaign['id'],
        headers={'Authorization': 'Bearer ' + token},
    )
    assert campaign_resp.status_code == 200
    campaign_data = campaign_resp.json()['data']
    assert 'snapshot' in campaign_data
    assert 'recommendation_success_rate' in campaign_data
    assert 'execution_success_rate' in campaign_data
    assert 'pattern_discovery_rate' in campaign_data
    assert 'learning_velocity' in campaign_data
    assert 'campaign_improvement_trend' in campaign_data

    system_resp = client.get('/api/v1/intelligence/metrics/system', headers={'Authorization': 'Bearer ' + token})
    assert system_resp.status_code == 200
    system_data = system_resp.json()['data']
    assert 'campaigns_tracked' in system_data
    assert 'recommendation_success_rate' in system_data
    assert 'execution_success_rate' in system_data
    assert 'pattern_discovery_rate' in system_data

    trends_resp = client.get(
        '/api/v1/intelligence/metrics/trends',
        params={'campaign_id': campaign['id'], 'days': 7},
        headers={'Authorization': 'Bearer ' + token},
    )
    assert trends_resp.status_code == 200
    trends_data = trends_resp.json()['data']
    assert trends_data['campaign_id'] == campaign['id']
    assert 'success_rate_over_time' in trends_data
    assert 'pattern_growth_rate' in trends_data
    assert 'policy_weight_changes' in trends_data
    assert 'average_outcome_delta' in trends_data
