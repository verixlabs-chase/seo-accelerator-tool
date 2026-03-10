from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.causal.causal_query_engine import get_policies_with_high_confidence, get_policies_with_positive_effect
from app.intelligence.evolution.evolution_models import PolicyMutationCandidate, StrongPolicyCandidate


def identify_strong_causal_policies(
    db: Session,
    *,
    industry: str,
    effect_threshold: float = 0.2,
    confidence_threshold: float = 0.7,
    limit: int = 20,
) -> list[StrongPolicyCandidate]:
    positive = {item.policy_id: item for item in get_policies_with_positive_effect(db, industry, limit=limit)}
    high_confidence = {item.policy_id: item for item in get_policies_with_high_confidence(db, industry=industry, min_confidence=confidence_threshold, limit=limit)}

    candidates: list[StrongPolicyCandidate] = []
    for policy_id, row in positive.items():
        if float(row.effect_size) <= effect_threshold:
            continue
        confidence_row = high_confidence.get(policy_id)
        confidence = float(confidence_row.confidence if confidence_row is not None else row.confidence)
        if confidence < confidence_threshold:
            continue
        candidates.append(
            StrongPolicyCandidate(
                policy_id=policy_id,
                industry=industry,
                effect_size=float(row.effect_size),
                confidence=confidence,
                sample_size=int(row.sample_size),
            )
        )

    candidates.sort(key=lambda item: (-item.confidence, -item.effect_size, -item.sample_size, item.policy_id))
    return candidates[:limit]


def generate_mutation_candidates(
    candidates: list[StrongPolicyCandidate],
    *,
    max_mutations_per_policy: int = 1,
    feature_targets: dict[str, str] | None = None,
) -> list[PolicyMutationCandidate]:
    mutations: list[PolicyMutationCandidate] = []
    seen: set[tuple[str, str]] = set()
    per_policy_cap = max(1, int(max_mutations_per_policy))
    generated_counts: dict[str, int] = {}
    for candidate in candidates:
        if int(generated_counts.get(candidate.policy_id, 0)) >= per_policy_cap:
            continue
        feature_name = (feature_targets or {}).get(candidate.policy_id)
        mutation_type, new_policy = _mutation_for_policy(candidate.policy_id, feature_name=feature_name)
        key = (candidate.policy_id, new_policy)
        if key in seen:
            continue
        seen.add(key)
        generated_counts[candidate.policy_id] = int(generated_counts.get(candidate.policy_id, 0)) + 1
        mutations.append(
            PolicyMutationCandidate(
                parent_policy=candidate.policy_id,
                new_policy=new_policy,
                mutation_type=mutation_type,
                industry=candidate.industry,
                expected_effect=round(candidate.effect_size * 1.1, 6),
                confidence=candidate.confidence,
            )
        )
    return mutations


def _mutation_for_policy(policy_id: str, *, feature_name: str | None = None) -> tuple[str, str]:
    mapping = {
        'increase_internal_links': ('amplify_internal_links', 'increase_internal_links_more'),
        'add_location_pages': ('cluster_location_pages', 'add_location_pages_cluster'),
    }
    if policy_id in mapping:
        return mapping[policy_id]

    feature_mapping = {
        'internal_link_ratio': ('target_internal_link_ratio', f'{policy_id}_internal_links_experimental'),
        'content_growth_rate': ('target_content_growth_rate', f'{policy_id}_content_growth_experimental'),
        'crawl_health_score': ('target_crawl_health_score', f'{policy_id}_crawl_health_experimental'),
        'technical_issue_density': ('target_technical_issue_density', f'{policy_id}_technical_cleanup_experimental'),
    }
    if feature_name in feature_mapping:
        return feature_mapping[feature_name]
    if policy_id.endswith('_more'):
        return ('iterate_policy_strength', f'{policy_id}_v2')
    return ('extend_policy_variant', f'{policy_id}_experimental')
