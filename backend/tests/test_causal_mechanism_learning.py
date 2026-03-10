from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.intelligence.causal_mechanisms.mechanism_learning_engine import learn_mechanisms_from_experiment_completed
from app.intelligence.causal.causal_learning_engine import learn_from_experiment_completed
from app.intelligence.evolution.strategy_evolution_engine import evolve_strategies
from app.models.campaign import Campaign
from app.models.causal_mechanism import FeatureImpactEdge, PolicyFeatureEdge
from app.models.temporal import TemporalSignalSnapshot, TemporalSignalType
from app.models.tenant import Tenant


def test_experiment_feature_deltas_create_mechanism_edges(db_session) -> None:
    tenant = Tenant(name='Mechanism Tenant', status='Active')
    db_session.add(tenant)
    db_session.flush()

    campaign = Campaign(tenant_id=tenant.id, name='Mechanism Campaign', domain='mechanism.example')
    db_session.add(campaign)
    db_session.flush()

    measured_at = datetime.now(UTC)
    db_session.add_all(
        [
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='internal_link_ratio',
                metric_value=0.3,
                observed_at=measured_at - timedelta(hours=1),
                source='feature_store_v1',
                confidence=0.9,
                version_hash='before-internal-link-ratio',
            ),
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='internal_link_ratio',
                metric_value=0.7,
                observed_at=measured_at + timedelta(hours=1),
                source='feature_store_v1',
                confidence=0.9,
                version_hash='after-internal-link-ratio',
            ),
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='crawl_health_score',
                metric_value=0.5,
                observed_at=measured_at - timedelta(hours=1),
                source='feature_store_v1',
                confidence=0.8,
                version_hash='before-crawl-health-score',
            ),
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.CUSTOM,
                metric_name='crawl_health_score',
                metric_value=0.8,
                observed_at=measured_at + timedelta(hours=1),
                source='feature_store_v1',
                confidence=0.8,
                version_hash='after-crawl-health-score',
            ),
        ]
    )
    db_session.commit()

    result = learn_mechanisms_from_experiment_completed(
        db_session,
        {
            'policy_id': 'increase_internal_links',
            'effect_size': 0.5,
            'confidence': 0.8,
            'industry': 'local',
            'sample_size': 10,
            'campaign_id': campaign.id,
            'measured_at': measured_at.isoformat(),
            'outcome_name': 'outcome::success',
        },
    )
    db_session.commit()

    assert result.feature_deltas == {
        'crawl_health_score': 0.3,
        'internal_link_ratio': 0.4,
    }

    policy_edges = {
        row.feature_name: row
        for row in db_session.query(PolicyFeatureEdge).filter(PolicyFeatureEdge.policy_id == 'increase_internal_links').all()
    }
    feature_edges = {
        row.feature_name: row
        for row in db_session.query(FeatureImpactEdge).filter(FeatureImpactEdge.policy_id == 'increase_internal_links').all()
    }

    assert float(policy_edges['internal_link_ratio'].effect_size) == 0.4
    assert float(policy_edges['crawl_health_score'].effect_size) == 0.3
    assert float(feature_edges['internal_link_ratio'].effect_size) == 0.2
    assert float(feature_edges['crawl_health_score'].effect_size) == 0.15


def test_feature_driven_evolution_targets_causal_driver_features(db_session) -> None:
    learn_from_experiment_completed(
        db_session,
        {
            'policy_id': 'generic_policy',
            'effect_size': 0.42,
            'confidence': 0.91,
            'sample_size': 18,
            'industry': 'local',
            'source_node': 'industry::local',
            'target_node': 'outcome::success',
        },
    )
    db_session.add(
        PolicyFeatureEdge(
            policy_id='generic_policy',
            feature_name='internal_link_ratio',
            effect_size=0.33,
            confidence=0.87,
            sample_size=15,
            industry='local',
        )
    )
    db_session.add(
        FeatureImpactEdge(
            policy_id='generic_policy',
            feature_name='internal_link_ratio',
            outcome_name='outcome::success',
            effect_size=0.21,
            confidence=0.93,
            sample_size=15,
            industry='local',
        )
    )
    db_session.commit()

    result = evolve_strategies(db_session, industry='local')

    assert [item.new_policy for item in result.mutations] == ['generic_policy_internal_links_experimental']
    assert result.mutations[0].mutation_type == 'target_internal_link_ratio'
