from app.services.operational_telemetry_service import (
    record_provider_call,
    record_replay_execution,
)


def _login(client, email: str, password: str) -> str:
    response = client.post('/api/v1/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200
    return response.json()['data']['access_token']


def test_operational_health_requires_platform_role(client) -> None:
    token = _login(client, 'org-admin@example.com', 'pass-org-admin')

    response = client.get(
        '/api/v1/system/operational-health',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 403


def test_operational_health_returns_expected_shape(client) -> None:
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
    assert payload['replay']['drift_status'] == 'clean'
    assert payload['provider_error_bands'][0]['provider'] == 'rank'
