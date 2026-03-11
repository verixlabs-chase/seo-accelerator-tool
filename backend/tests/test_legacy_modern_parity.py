from __future__ import annotations

# Legacy runtime removed.
# This test now verifies that the modern knowledge-graph learning pipeline
# still produces equivalent diagnostic observability without executing
# the deprecated legacy learning system.

from types import SimpleNamespace

from app.intelligence.intelligence_orchestrator import run_campaign_cycle
from app.intelligence.legacy_adapters.diagnostic_adapter import collect_legacy_diagnostics
from app.intelligence.signal_assembler import assemble_signals
from app.models.intelligence import StrategyRecommendation
from tests.conftest import create_test_campaign


def test_modern_runtime_preserves_legacy_diagnostic_coverage(
    db_session,
    create_test_tenant,
    create_test_org,
    monkeypatch,
) -> None:
    tenant = create_test_tenant(name='Parity Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Parity Org')
    org.plan_type = 'enterprise'
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Parity Campaign', domain='parity.example')
    campaign.setup_state = 'Active'
    db_session.commit()

    signals = assemble_signals(campaign.id, db=db_session, publish=False)
    diagnostics = collect_legacy_diagnostics(
        campaign_id=campaign.id,
        raw_signals=signals,
        db=db_session,
        tier='enterprise',
    )
    expected_scenarios = {item.scenario_id for item in diagnostics}

    monkeypatch.setattr(
        'app.intelligence.intelligence_orchestrator._select_recommendations_via_digital_twin',
        lambda _db, *, campaign_id, recommendations: (
            recommendations,
            {'status': 'stubbed', 'campaign_id': campaign_id, 'selected_recommendation_ids': [row.id for row in recommendations]},
        ),
    )
    monkeypatch.setattr(
        'app.intelligence.intelligence_orchestrator._schedule_recommendation_executions',
        lambda _db, _recommendations: [],
    )
    monkeypatch.setattr(
        'app.intelligence.intelligence_orchestrator._execute_scheduled_executions',
        lambda _db, _executions: [],
    )
    monkeypatch.setattr(
        'app.intelligence.intelligence_orchestrator.compute_campaign_metrics',
        lambda *args, **kwargs: SimpleNamespace(id='parity-metric', metric_date=kwargs['metric_date']),
    )

    modern = run_campaign_cycle(campaign.id, db=db_session)
    modern_packaging = modern['legacy_packaging']
    persisted = db_session.query(StrategyRecommendation).filter(StrategyRecommendation.campaign_id == campaign.id).all()

    assert modern['signals_processed'] > 0
    assert modern['features_computed'] > 0
    assert modern['recommendations_generated'] >= 0
    assert persisted
    assert expected_scenarios.issubset(set(modern_packaging['detected_scenarios']))
    assert modern_packaging['executive_summary']['top_priority_scenario'] in set(modern_packaging['detected_scenarios']) | {None}
    assert modern_packaging['strategic_scores']['strategy_score'] >= 0


def test_legacy_diagnostics_adapter_matches_legacy_engine_scenarios(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Diag Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Diag Org')
    org.plan_type = 'enterprise'
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Diag Campaign', domain='diag.example')
    db_session.commit()

    signals = assemble_signals(campaign.id, db=db_session, publish=False)
    diagnostics = collect_legacy_diagnostics(campaign_id=campaign.id, raw_signals=signals, db=db_session, tier='enterprise')
    scenario_ids = {item.scenario_id for item in diagnostics}

    assert 'competitor_data_unavailable' in scenario_ids
