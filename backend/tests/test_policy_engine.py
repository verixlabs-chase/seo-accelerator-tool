from __future__ import annotations

from app.intelligence.policy_engine import derive_policy, generate_recommendations, score_policy


def test_policy_engine_derives_scores_and_generates_recommendations() -> None:
    patterns = [
        {
            'pattern_key': 'internal_link_problem',
            'confidence': 0.82,
            'evidence': ['technical_issue_density', 'internal_link_ratio'],
        }
    ]
    features = {
        'internal_link_ratio': 0.32,
        'technical_issue_density': 0.45,
        'ranking_velocity': -0.05,
    }

    policies = derive_policy(patterns)
    assert policies
    assert policies[0]['policy_id'] == 'prioritize_internal_linking'

    scored = score_policy(policies[0], features)
    assert scored['priority_score'] > 0.7
    assert 0 <= scored['confidence_score'] <= 1

    recommendations = generate_recommendations(scored)
    assert recommendations
    assert recommendations[0]['recommendation_type'].startswith('policy::prioritize_internal_linking::')
