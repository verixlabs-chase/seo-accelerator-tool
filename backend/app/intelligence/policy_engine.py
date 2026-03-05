from __future__ import annotations

from typing import Any

_POLICY_LIBRARY: dict[str, dict[str, Any]] = {
    'prioritize_internal_linking': {
        'priority_weight': 0.75,
        'risk_tier': 1,
        'recommended_actions': ['add_contextual_links', 'audit_navigation_links'],
    },
    'stabilize_visibility_with_content_refresh': {
        'priority_weight': 0.7,
        'risk_tier': 2,
        'recommended_actions': ['refresh_declining_pages', 'expand_supporting_content'],
    },
    'accelerate_content_velocity': {
        'priority_weight': 0.65,
        'risk_tier': 2,
        'recommended_actions': ['increase_content_throughput', 'publish_cluster_support_pages'],
    },
}

_PATTERN_POLICY_MAP: dict[str, str] = {
    'internal_link_problem': 'prioritize_internal_linking',
    'internal_link_deficit': 'prioritize_internal_linking',
    'declining_visibility_with_low_content_growth': 'stabilize_visibility_with_content_refresh',
    'cohort_content_growth_lag': 'accelerate_content_velocity',
}


def derive_policy(patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    for pattern in patterns:
        pattern_key = str(pattern.get('pattern_key', '') or '')
        if not pattern_key:
            continue

        policy_id = _PATTERN_POLICY_MAP.get(pattern_key)
        if policy_id is None:
            continue

        base = _POLICY_LIBRARY[policy_id]
        confidence = float(pattern.get('confidence', 0.5) or 0.5)

        existing = grouped.get(policy_id)
        if existing is None:
            grouped[policy_id] = {
                'policy_id': policy_id,
                'priority_weight': float(base['priority_weight']),
                'risk_tier': int(base['risk_tier']),
                'recommended_actions': list(base['recommended_actions']),
                'source_patterns': [pattern_key],
                'pattern_confidence': confidence,
            }
            continue

        existing['source_patterns'] = sorted(set(existing['source_patterns'] + [pattern_key]))
        existing['pattern_confidence'] = max(float(existing['pattern_confidence']), confidence)

    return [grouped[key] for key in sorted(grouped)]


def score_policy(policy: dict[str, Any], features: dict[str, float]) -> dict[str, Any]:
    scored = dict(policy)
    policy_id = str(policy.get('policy_id', '') or '')
    base_weight = float(policy.get('priority_weight', 0.5) or 0.5)
    pattern_confidence = float(policy.get('pattern_confidence', 0.5) or 0.5)

    internal_link_ratio = float(features.get('internal_link_ratio', 1.0) or 1.0)
    technical_issue_density = float(features.get('technical_issue_density', 0.0) or 0.0)
    ranking_velocity = float(features.get('ranking_velocity', 0.0) or 0.0)

    signal_boost = 0.0
    if policy_id == 'prioritize_internal_linking':
        signal_boost += max(0.0, 0.7 - internal_link_ratio) * 0.6
        signal_boost += min(technical_issue_density, 1.0) * 0.2
    elif policy_id == 'stabilize_visibility_with_content_refresh':
        signal_boost += max(0.0, -ranking_velocity) * 0.5
    elif policy_id == 'accelerate_content_velocity':
        content_growth_rate = float(features.get('content_growth_rate', 0.0) or 0.0)
        signal_boost += max(0.0, 0.1 - content_growth_rate) * 0.5

    priority_score = max(0.0, min(1.0, base_weight * 0.7 + pattern_confidence * 0.2 + signal_boost))

    scored['priority_score'] = round(priority_score, 6)
    scored['confidence_score'] = round(max(0.0, min(1.0, pattern_confidence)), 6)
    return scored


def generate_recommendations(policy: dict[str, Any]) -> list[dict[str, Any]]:
    policy_id = str(policy.get('policy_id', '') or '')
    risk_tier = int(policy.get('risk_tier', 2) or 2)
    priority_score = float(policy.get('priority_score', policy.get('priority_weight', 0.5)) or 0.5)
    actions = [str(item) for item in policy.get('recommended_actions', [])]

    recommendations: list[dict[str, Any]] = []
    for action in actions:
        recommendations.append(
            {
                'recommendation_type': f'policy::{policy_id}::{action}',
                'policy_id': policy_id,
                'action': action,
                'priority_weight': round(priority_score, 6),
                'risk_tier': risk_tier,
                'rationale': f'Deterministic policy action derived from {policy_id}',
            }
        )

    return recommendations
