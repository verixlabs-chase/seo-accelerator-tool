from __future__ import annotations

import json

from app.enums import StrategyRecommendationStatus
from app.intelligence.recommendation_execution_engine import schedule_execution
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.models.user import User
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


RETRY_LIMIT = 3


def _login(client, email: str, password: str) -> str:
    response = client.post('/api/v1/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200
    return response.json()['data']['access_token']


def _create_recommendation(db_session, tenant_id: str, campaign_id: str, recommendation_type: str) -> StrategyRecommendation:
    rec = StrategyRecommendation(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        recommendation_type=recommendation_type,
        rationale='api test',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='[]',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(rec)
    db_session.commit()
    return rec


def test_execution_api_run_retry_cancel_flow(client, db_session, create_test_org) -> None:
    token = _login(client, 'org-admin@example.com', 'pass-org-admin')
    acting_user = db_session.query(User).filter(User.email == 'org-admin@example.com').first()
    assert acting_user is not None
    tenant_id = acting_user.tenant_id

    org = create_test_org(tenant_id=tenant_id, name='API Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant_id,
        name='API Campaign',
        domain='api-exec.example',
    )

    rec = _create_recommendation(db_session, tenant_id, campaign.id, 'improve_internal_links')
    execution = schedule_execution(rec.id, db=db_session)
    assert execution is not None

    list_resp = client.get(
        '/api/v1/executions',
        params={'campaign_id': campaign.id},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()['data']['items']) >= 1

    get_resp = client.get(
        f'/api/v1/executions/{execution.id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()['data']['id'] == execution.id

    dry_run_resp = client.post(
        f'/api/v1/executions/{execution.id}/run',
        json={'dry_run': True},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert dry_run_resp.status_code == 200
    dry_payload = dry_run_resp.json()['data']
    assert dry_payload['dry_run'] is True
    assert dry_payload['result']['status'] == 'planned'

    run_resp = client.post(
        f'/api/v1/executions/{execution.id}/run',
        json={'dry_run': False},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert run_resp.status_code == 200
    assert run_resp.json()['data']['status'] in {'completed', 'failed'}

    completed_cancel_resp = client.post(
        f'/api/v1/executions/{execution.id}/cancel',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert completed_cancel_resp.status_code == 400

    failed_execution = RecommendationExecution(
        recommendation_id=rec.id,
        campaign_id=campaign.id,
        execution_type='fix_missing_title',
        execution_payload=json.dumps(
            {
                'recommendation_id': rec.id,
                'campaign_id': campaign.id,
                'tenant_id': tenant_id,
                'metric_name': 'technical_issue_count',
                'metric_before': 0.0,
                'idempotency_key': 'failed-api-retry',
            },
            sort_keys=True,
        ),
        idempotency_key='failed-api-retry',
        deterministic_hash='deadbeef' * 8,
        status='failed',
        attempt_count=0,
    )
    db_session.add(failed_execution)
    db_session.commit()

    retry_resp = client.post(
        f'/api/v1/executions/{failed_execution.id}/retry',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert retry_resp.status_code == 200
    assert retry_resp.json()['data']['attempt_count'] >= 1

    scheduled_execution = RecommendationExecution(
        recommendation_id=rec.id,
        campaign_id=campaign.id,
        execution_type='fix_missing_title',
        execution_payload=json.dumps(
            {
                'recommendation_id': rec.id,
                'campaign_id': campaign.id,
                'tenant_id': tenant_id,
                'metric_name': 'technical_issue_count',
                'metric_before': 0.0,
                'idempotency_key': 'cancel-scheduled',
            },
            sort_keys=True,
        ),
        idempotency_key='cancel-scheduled',
        deterministic_hash='abcddcba' * 8,
        status='scheduled',
        attempt_count=0,
    )
    db_session.add(scheduled_execution)
    db_session.commit()

    cancel_resp = client.post(
        f'/api/v1/executions/{scheduled_execution.id}/cancel',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()['data']['status'] == 'failed'

    capped_execution = RecommendationExecution(
        recommendation_id=rec.id,
        campaign_id=campaign.id,
        execution_type='fix_missing_title',
        execution_payload=json.dumps(
            {
                'recommendation_id': rec.id,
                'campaign_id': campaign.id,
                'tenant_id': tenant_id,
                'metric_name': 'technical_issue_count',
                'metric_before': 0.0,
                'idempotency_key': 'retry-capped',
            },
            sort_keys=True,
        ),
        idempotency_key='retry-capped',
        deterministic_hash='feedface' * 8,
        status='failed',
        attempt_count=RETRY_LIMIT,
    )
    db_session.add(capped_execution)
    db_session.commit()

    capped_retry_resp = client.post(
        f'/api/v1/executions/{capped_execution.id}/retry',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert capped_retry_resp.status_code == 200
    assert capped_retry_resp.json()['data']['attempt_count'] == RETRY_LIMIT
    assert capped_retry_resp.json()['data']['status'] == 'failed'
