from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.organization import Organization
from app.models.strategy_execution_key import StrategyExecutionKey
from app.models.temporal import MomentumMetric, StrategyPhaseHistory, TemporalSignalSnapshot, TemporalSignalType


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


def _set_org_plan(db_session, org_id: str, plan_type: str) -> None:  # noqa: ANN001
    org = db_session.query(Organization).filter(Organization.id == org_id).first()
    assert org is not None
    org.plan_type = plan_type
    db_session.commit()


def test_campaign_strategy_exposes_temporal_fields_and_persists_phase(client, db_session) -> None:
    token, tenant_id = _login(client, 'org-admin@example.com', 'pass-org-admin')
    _set_org_plan(db_session, tenant_id, 'enterprise')
    campaign = _create_campaign(client, token, 'Temporal Phase', 'temporal-phase.example')

    start = datetime(2026, 2, 1, tzinfo=UTC)
    rank_values = [8.0, 7.0, 6.0, 5.0]
    for idx, value in enumerate(rank_values):
        db_session.add(
            TemporalSignalSnapshot(
                campaign_id=campaign['id'],
                signal_type=TemporalSignalType.RANK,
                metric_name='avg_position',
                metric_value=value,
                observed_at=start + timedelta(days=idx),
                source='test-seed',
                confidence=1.0,
                version_hash='seed-v1',
            )
        )
    db_session.commit()

    response = client.get(
        f"/api/v1/campaigns/{campaign['id']}/strategy",
        params={'date_from': '2026-02-01T00:00:00Z', 'date_to': '2026-02-20T00:00:00Z'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == 200
    data = response.json()['data']

    assert 'current_strategy_phase' in data
    assert 'momentum_score' in data
    assert 'trend_direction' in data
    assert 'volatility_level' in data
    assert data['trend_direction'] == 'improving'

    phase_rows = db_session.query(StrategyPhaseHistory).filter(StrategyPhaseHistory.campaign_id == campaign['id']).all()
    metric_rows = db_session.query(MomentumMetric).filter(MomentumMetric.campaign_id == campaign['id']).all()
    assert len(phase_rows) >= 1
    assert len(metric_rows) >= 1

    # Execution metadata should carry deterministic profile version context.
    execution_row = (
        db_session.query(StrategyExecutionKey)
        .filter(StrategyExecutionKey.campaign_id == campaign['id'])
        .order_by(StrategyExecutionKey.created_at.desc())
        .first()
    )
    assert execution_row is not None
    assert execution_row.version_fingerprint
