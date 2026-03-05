from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.strategy_memory_pattern import StrategyMemoryPattern
from app.services.strategy_engine.engine import build_campaign_strategy
from app.services.strategy_engine.schemas import StrategyWindow
from tests.conftest import create_test_campaign


def _priority_for(recommendations, scenario_id: str) -> float:
    for rec in recommendations:
        if rec.scenario_id == scenario_id:
            return float(rec.priority_score)
    raise AssertionError(f'Missing scenario: {scenario_id}')


def test_strategy_engine_applies_strategy_memory_multiplier(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Memory Integration Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Memory Integration Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Memory Integration Campaign',
        domain='memory-integration.example',
    )
    db_session.commit()

    window = StrategyWindow(
        date_from=datetime.now(UTC) - timedelta(days=30),
        date_to=datetime.now(UTC),
    )
    raw_signals = {
        'position_delta': 6.0,
        'traffic_growth_percent': -0.3,
    }

    baseline = build_campaign_strategy(
        campaign_id=campaign.id,
        window=window,
        raw_signals=raw_signals,
        tier='pro',
        db=db_session,
    )
    baseline_priority = _priority_for(baseline.recommendations, 'ranking_decline_detected')

    db_session.add(
        StrategyMemoryPattern(
            pattern_name='ranking_velocity_drag_recovery',
            feature_name='ranking_velocity',
            pattern_description='memory multiplier pattern',
            support_count=12,
            avg_outcome_delta=1.8,
            confidence_score=0.8,
        )
    )
    db_session.commit()

    memory_influenced = build_campaign_strategy(
        campaign_id=campaign.id,
        window=window,
        raw_signals=raw_signals,
        tier='pro',
        db=db_session,
    )
    memory_priority = _priority_for(memory_influenced.recommendations, 'ranking_decline_detected')

    assert memory_priority < baseline_priority


def test_strategy_memory_api_endpoints(client, db_session) -> None:
    login = client.post('/api/v1/auth/login', json={'email': 'org-admin@example.com', 'password': 'pass-org-admin'})
    assert login.status_code == 200
    token = login.json()['data']['access_token']

    row = StrategyMemoryPattern(
        pattern_name='api_memory_pattern',
        feature_name='technical_issue_density',
        pattern_description='api test',
        support_count=20,
        avg_outcome_delta=2.0,
        confidence_score=0.9,
    )
    db_session.add(row)
    db_session.commit()

    list_resp = client.get('/api/v1/strategy-memory/patterns', headers={'Authorization': f'Bearer {token}'})
    assert list_resp.status_code == 200
    assert len(list_resp.json()['data']['items']) >= 1

    top_resp = client.get('/api/v1/strategy-memory/patterns/top', headers={'Authorization': f'Bearer {token}'})
    assert top_resp.status_code == 200
    assert len(top_resp.json()['data']['items']) >= 1

    get_resp = client.get(f'/api/v1/strategy-memory/patterns/{row.id}', headers={'Authorization': f'Bearer {token}'})
    assert get_resp.status_code == 200
    assert get_resp.json()['data']['id'] == row.id
