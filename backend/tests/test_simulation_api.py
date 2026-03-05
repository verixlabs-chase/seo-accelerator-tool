from app.enums import StrategyRecommendationStatus
from app.models.digital_twin_simulation import DigitalTwinSimulation
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_outcome import RecommendationOutcome
from app.utils.enum_guard import ensure_enum


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


def test_simulation_api_returns_history(client, db_session) -> None:
    token = _login(client, 'org-admin@example.com', 'pass-org-admin')
    campaign = _create_campaign(client, token, 'Simulation API Campaign', 'sim-api.example')

    recommendation = StrategyRecommendation(
        tenant_id=campaign['tenant_id'],
        campaign_id=campaign['id'],
        recommendation_type='create_content_brief',
        rationale='simulation api test',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='{}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
        idempotency_key='simulation-api-test',
    )
    db_session.add(recommendation)
    db_session.flush()

    first = DigitalTwinSimulation(
        campaign_id=campaign['id'],
        strategy_actions=[{'type': 'internal_link', 'count': 2}],
        predicted_rank_delta=0.4,
        predicted_traffic_delta=3.2,
        confidence=0.61,
        expected_value=0.244,
        selected_strategy=False,
        model_version='rank=v1;traffic=v1;confidence=v1',
    )
    second = DigitalTwinSimulation(
        campaign_id=campaign['id'],
        strategy_actions=[{'type': 'publish_content', 'pages': 2}],
        predicted_rank_delta=0.9,
        predicted_traffic_delta=7.2,
        confidence=0.72,
        expected_value=0.648,
        selected_strategy=True,
        model_version='rank=v1;traffic=v1;confidence=v1',
    )
    db_session.add_all([first, second])
    db_session.flush()

    db_session.add(
        RecommendationOutcome(
            recommendation_id=recommendation.id,
            campaign_id=campaign['id'],
            simulation_id=second.id,
            metric_before=10.0,
            metric_after=11.0,
            delta=1.0,
        )
    )
    db_session.commit()

    response = client.get(
        '/api/v1/intelligence/simulations/campaign/' + campaign['id'],
        params={'limit': 10},
        headers={'Authorization': 'Bearer ' + token},
    )
    assert response.status_code == 200

    payload = response.json()['data']
    assert payload['campaign_id'] == campaign['id']
    assert payload['count'] == 2
    assert len(payload['items']) == 2
    assert all('strategy_actions' in item for item in payload['items'])
    assert all('predicted_rank_delta' in item for item in payload['items'])
    assert all('predicted_traffic_delta' in item for item in payload['items'])
    assert any(item['selected_strategy'] is True for item in payload['items'])

    selected = next(item for item in payload['items'] if item['selected_strategy'])
    assert selected['actual_rank_delta'] == 1.0
    assert selected['actual_traffic_delta'] == 1.0
    assert selected['prediction_error_rank'] == abs(selected['predicted_rank_delta'] - 1.0)
    assert selected['prediction_error_traffic'] == abs(selected['predicted_traffic_delta'] - 1.0)
