from __future__ import annotations

from app.intelligence.intelligence_orchestrator import run_campaign_cycle
from app.intelligence.legacy_adapters.diagnostic_adapter import collect_legacy_diagnostics
from app.intelligence.signal_assembler import assemble_signals, recent_window_bounds
from app.services.strategy_engine.engine import build_campaign_strategy
from app.services.strategy_engine.schemas import StrategyWindow
from tests.conftest import create_test_campaign


def test_modern_runtime_preserves_legacy_diagnostic_coverage(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Parity Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Parity Org')
    org.plan_type = 'enterprise'
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Parity Campaign', domain='parity.example')
    campaign.setup_state = 'Active'
    db_session.commit()

    start, end = recent_window_bounds(30)
    window = StrategyWindow(date_from=start, date_to=end)
    legacy = build_campaign_strategy(
        campaign.id,
        window,
        assemble_signals(campaign.id, db=db_session, publish=False),
        tier='enterprise',
        db=db_session,
    )

    modern = run_campaign_cycle(campaign.id, db=db_session)
    modern_packaging = modern['legacy_packaging']

    assert set(legacy.detected_scenarios).issubset(set(modern_packaging['detected_scenarios']))
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
