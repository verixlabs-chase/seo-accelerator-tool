from __future__ import annotations

from app.enums import StrategyRecommendationStatus
from app.intelligence.recommendation_execution_engine import execute_recommendation, schedule_execution
from app.models.intelligence import StrategyRecommendation
from app.models.user import User
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


def _login(client, email: str, password: str) -> str:
    response = client.post('/api/v1/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200
    return response.json()['data']['access_token']


def test_execution_rollback_api(client, db_session, create_test_org) -> None:
    token = _login(client, 'org-admin@example.com', 'pass-org-admin')
    acting_user = db_session.query(User).filter(User.email == 'org-admin@example.com').first()
    assert acting_user is not None
    org = create_test_org(tenant_id=acting_user.tenant_id, name='Rollback API Org')
    campaign = create_test_campaign(db_session, org.id, tenant_id=acting_user.tenant_id, name='Rollback API Campaign', domain='rollback-api.example')
    recommendation = StrategyRecommendation(
        tenant_id=acting_user.tenant_id,
        campaign_id=campaign.id,
        recommendation_type='fix_missing_title',
        rationale='rollback api test',
        confidence=0.9,
        confidence_score=0.9,
        evidence_json='{}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(recommendation)
    db_session.commit()
    execution = schedule_execution(recommendation.id, db=db_session)
    assert execution is not None
    executed = execute_recommendation(execution.id, db=db_session)
    assert executed is not None
    assert executed.status == 'completed'
    response = client.post(
        f'/api/v1/executions/{execution.id}/rollback',
        json={'requested_by': 'api-tester'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == 200
    payload = response.json()['data']
    assert payload['status'] == 'rolled_back'
    assert payload['rolled_back_at'] is not None
