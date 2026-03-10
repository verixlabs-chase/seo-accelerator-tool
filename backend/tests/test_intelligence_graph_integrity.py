from __future__ import annotations

from app.models.campaign import Campaign
from app.models.experiment import Experiment, ExperimentAssignment
from app.models.intelligence import StrategyRecommendation
from app.models.policy_performance import PolicyPerformance
from app.models.tenant import Tenant


def test_intelligence_graph_integrity(db_session, intelligence_graph) -> None:
    graph = intelligence_graph

    assert db_session.query(Tenant).filter(Tenant.id == graph['tenant'].id).count() == 1

    for campaign in graph['campaigns']:
        persisted = db_session.get(Campaign, campaign.id)
        assert persisted is not None
        assert persisted.tenant_id == graph['tenant'].id

    for recommendation in graph['recommendations']:
        persisted = db_session.get(StrategyRecommendation, recommendation.id)
        assert persisted is not None
        assert db_session.get(Campaign, persisted.campaign_id) is not None

    for experiment in graph['experiments']:
        persisted = db_session.get(Experiment, experiment.experiment_id)
        assert persisted is not None

    for assignment in graph['assignments']:
        persisted = db_session.get(ExperimentAssignment, assignment.id)
        assert persisted is not None
        assert db_session.get(Campaign, persisted.campaign_id) is not None
        assert db_session.get(Experiment, persisted.experiment_id) is not None

    for row in graph['policy_performance']:
        persisted = db_session.get(PolicyPerformance, row.id)
        assert persisted is not None
        assert db_session.get(Campaign, persisted.campaign_id) is not None
