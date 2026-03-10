from __future__ import annotations

from app.intelligence.intelligence_orchestrator import run_campaign_cycle, run_system_cycle
from app.models.intelligence import StrategyRecommendation
from app.models.intelligence_metrics_snapshot import IntelligenceMetricsSnapshot
from app.models.recommendation_execution import RecommendationExecution
from app.models.temporal import TemporalSignalSnapshot
from tests.conftest import create_test_campaign


def test_run_campaign_cycle_wires_pipeline(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Orchestrator Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Orchestrator Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Orchestrator Campaign',
        domain='orchestrator.example',
    )
    campaign.setup_state = 'Active'
    db_session.commit()

    summary = run_campaign_cycle(campaign.id, db=db_session)

    assert summary['campaign_id'] == campaign.id
    assert summary['signals_processed'] > 0
    assert summary['features_computed'] > 0
    assert summary['recommendations_generated'] > 0
    assert summary['executions_scheduled'] > 0
    assert summary['executions_completed'] > 0

    temporal_rows = (
        db_session.query(TemporalSignalSnapshot)
        .filter(
            TemporalSignalSnapshot.campaign_id == campaign.id,
            TemporalSignalSnapshot.source.in_(['orchestrator_signal_assembler_v1', 'feature_store_v1']),
        )
        .count()
    )
    assert temporal_rows > 0

    recommendation_rows = (
        db_session.query(StrategyRecommendation)
        .filter(StrategyRecommendation.campaign_id == campaign.id)
        .all()
    )
    assert recommendation_rows
    assert all(len(row.recommendation_type) <= 128 for row in recommendation_rows)
    assert all(len(row.idempotency_key or '') <= 128 for row in recommendation_rows)
    assert all('Increase review request coverage across touchpoints.' not in row.recommendation_type for row in recommendation_rows)

    execution_rows = (
        db_session.query(RecommendationExecution)
        .filter(RecommendationExecution.campaign_id == campaign.id)
        .count()
    )
    assert execution_rows > 0

    snapshot = (
        db_session.query(IntelligenceMetricsSnapshot)
        .filter(IntelligenceMetricsSnapshot.campaign_id == campaign.id)
        .order_by(IntelligenceMetricsSnapshot.metric_date.desc())
        .first()
    )
    assert snapshot is not None


def test_run_system_cycle_processes_active_campaigns(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='System Orchestrator Tenant')
    org = create_test_org(tenant_id=tenant.id, name='System Orchestrator Org')

    active_campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Active Campaign',
        domain='active-orchestrator.example',
    )
    active_campaign.setup_state = 'Active'

    draft_campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Draft Campaign',
        domain='draft-orchestrator.example',
    )
    draft_campaign.setup_state = 'Draft'
    db_session.commit()

    summary = run_system_cycle(db=db_session)

    assert summary['campaigns_processed'] >= 1
    assert active_campaign.id in summary['campaign_ids']
    assert draft_campaign.id not in summary['campaign_ids']
