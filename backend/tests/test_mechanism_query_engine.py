from __future__ import annotations

from app.intelligence.causal_mechanisms.mechanism_query_engine import (
    get_features_most_influencing_outcome,
    get_policies_affecting_feature,
    get_strategies_for_feature_improvement,
)
from app.models.causal_mechanism import FeatureImpactEdge, PolicyFeatureEdge


def test_mechanism_queries_return_expected_policy_and_feature_rankings(db_session) -> None:
    db_session.add_all(
        [
            PolicyFeatureEdge(policy_id='policy-a', feature_name='internal_link_ratio', effect_size=0.4, confidence=0.95, sample_size=12, industry='local'),
            PolicyFeatureEdge(policy_id='policy-b', feature_name='internal_link_ratio', effect_size=0.3, confidence=0.85, sample_size=14, industry='local'),
            PolicyFeatureEdge(policy_id='policy-c', feature_name='content_growth_rate', effect_size=0.5, confidence=0.9, sample_size=11, industry='local'),
            FeatureImpactEdge(policy_id='policy-a', feature_name='internal_link_ratio', outcome_name='outcome::success', effect_size=0.18, confidence=0.95, sample_size=12, industry='local'),
            FeatureImpactEdge(policy_id='policy-b', feature_name='internal_link_ratio', outcome_name='outcome::success', effect_size=0.12, confidence=0.85, sample_size=14, industry='local'),
            FeatureImpactEdge(policy_id='policy-c', feature_name='content_growth_rate', outcome_name='outcome::success', effect_size=0.11, confidence=0.9, sample_size=11, industry='local'),
        ]
    )
    db_session.commit()

    policies = get_policies_affecting_feature(db_session, 'internal_link_ratio', industry='local')
    features = get_features_most_influencing_outcome(db_session, 'outcome::success', industry='local')
    strategies = get_strategies_for_feature_improvement(db_session, 'internal_link_ratio', industry='local')

    assert [item.policy_id for item in policies] == ['policy-a', 'policy-b']
    assert [item.feature_name for item in features[:2]] == ['internal_link_ratio', 'content_growth_rate']
    assert [item.policy_id for item in strategies] == ['policy-a', 'policy-b']
