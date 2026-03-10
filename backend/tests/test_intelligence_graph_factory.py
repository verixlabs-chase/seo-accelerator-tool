from __future__ import annotations

from app.models.campaign import Campaign
from app.models.experiment import Experiment, ExperimentAssignment
from app.models.intelligence import StrategyRecommendation
from app.models.policy_performance import PolicyPerformance
from app.models.strategy_evolution_log import StrategyEvolutionLog
from app.models.tenant import Tenant


def test_intelligence_graph_factory_creates_fk_safe_graph(db_session, intelligence_graph) -> None:
    graph = intelligence_graph

    assert isinstance(graph['tenant'], Tenant)
    assert len(graph['campaigns']) == 4
    assert len(graph['recommendations']) == 4
    assert len(graph['experiments']) == 2
    assert len(graph['assignments']) == 4
    assert len(graph['policy_performance']) == 4
    assert len(graph['evolution_logs']) == 2

    assert db_session.query(Tenant).filter(Tenant.id == graph['tenant'].id).count() == 1
    assert db_session.query(Campaign).count() >= 4
    assert db_session.query(StrategyRecommendation).filter(StrategyRecommendation.id.in_(['r1', 'r2', 'r3', 'r4'])).count() == 4
    assert db_session.query(Experiment).count() >= 2
    assert db_session.query(ExperimentAssignment).count() >= 4
    assert db_session.query(PolicyPerformance).count() >= 4
    assert db_session.query(StrategyEvolutionLog).count() >= 2

    assignment = db_session.query(ExperimentAssignment).filter(ExperimentAssignment.campaign_id == 'camp-2').one()
    assert assignment.assigned_policy_id == 'child-a'
