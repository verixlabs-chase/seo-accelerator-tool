from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.causal_mechanisms.mechanism_query_engine import (
    get_features_most_influencing_outcome,
    get_strategies_for_feature_improvement,
)
from app.intelligence.evolution.evolution_models import StrategyEvolutionResult
from app.intelligence.evolution.policy_mutation_engine import register_mutated_policies
from app.intelligence.evolution.strategy_generator import generate_mutation_candidates, identify_strong_causal_policies
from app.models.experiment import Experiment

DEFAULT_EFFECT_THRESHOLD = 0.2
DEFAULT_CONFIDENCE_THRESHOLD = 0.7
DEFAULT_MAX_MUTATIONS_PER_POLICY = 1
DEFAULT_MAX_NEW_EXPERIMENTS_PER_CYCLE = 5


def evolve_strategies(
    db: Session,
    *,
    industry: str,
    effect_threshold: float = DEFAULT_EFFECT_THRESHOLD,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    limit: int = 10,
    max_mutations_per_policy: int = DEFAULT_MAX_MUTATIONS_PER_POLICY,
    max_new_experiments_per_cycle: int = DEFAULT_MAX_NEW_EXPERIMENTS_PER_CYCLE,
) -> StrategyEvolutionResult:
    candidates = identify_strong_causal_policies(
        db,
        industry=industry,
        effect_threshold=effect_threshold,
        confidence_threshold=confidence_threshold,
        limit=limit,
    )
    feature_targets = _feature_targets_by_policy(db, industry=industry, candidates=candidates)
    mutations = generate_mutation_candidates(
        candidates,
        max_mutations_per_policy=max_mutations_per_policy,
        feature_targets=feature_targets,
    )
    registered = register_mutated_policies(db, mutations)
    experiments = _ensure_experiments(
        db,
        registered,
        industry=industry,
        max_new_experiments_per_cycle=max_new_experiments_per_cycle,
    )
    db.flush()
    return StrategyEvolutionResult(
        candidates=candidates,
        mutations=mutations,
        registered_policies=registered,
        experiments_triggered=experiments,
    )


def process(db: Session, payload: dict[str, object]) -> dict[str, object]:
    industry = str(payload.get('industry', '') or 'unknown').strip() or 'unknown'
    effect_threshold = float(payload.get('effect_threshold', DEFAULT_EFFECT_THRESHOLD) or DEFAULT_EFFECT_THRESHOLD)
    confidence_threshold = float(payload.get('confidence', payload.get('confidence_threshold', DEFAULT_CONFIDENCE_THRESHOLD)) or DEFAULT_CONFIDENCE_THRESHOLD)
    result = evolve_strategies(
        db,
        industry=industry,
        effect_threshold=effect_threshold,
        confidence_threshold=min(max(confidence_threshold, 0.0), 1.0),
        limit=int(payload.get('limit', 10) or 10),
        max_mutations_per_policy=int(payload.get('max_mutations_per_policy', DEFAULT_MAX_MUTATIONS_PER_POLICY) or DEFAULT_MAX_MUTATIONS_PER_POLICY),
        max_new_experiments_per_cycle=int(payload.get('max_new_experiments_per_cycle', DEFAULT_MAX_NEW_EXPERIMENTS_PER_CYCLE) or DEFAULT_MAX_NEW_EXPERIMENTS_PER_CYCLE),
    )
    return {
        'industry': industry,
        'candidates': [item.model_dump(mode='json') for item in result.candidates],
        'mutations': [item.model_dump(mode='json') for item in result.mutations],
        'registered_policies': [item.model_dump(mode='json') for item in result.registered_policies],
        'experiments_triggered': list(result.experiments_triggered),
    }




def _feature_targets_by_policy(db: Session, *, industry: str, candidates: list) -> dict[str, str]:
    candidate_ids = {item.policy_id for item in candidates}
    if not candidate_ids:
        return {}

    targets: dict[str, str] = {}
    drivers = get_features_most_influencing_outcome(db, 'outcome::success', industry=industry, limit=5)
    for driver in drivers:
        for policy in get_strategies_for_feature_improvement(db, driver.feature_name, industry=industry, limit=25):
            if policy.policy_id in candidate_ids and policy.policy_id not in targets:
                targets[policy.policy_id] = driver.feature_name
    return targets
def _ensure_experiments(
    db: Session,
    registered: list,
    *,
    industry: str,
    max_new_experiments_per_cycle: int,
) -> list[str]:
    experiment_ids: list[str] = []
    new_experiments = 0
    cap = max(0, int(max_new_experiments_per_cycle))
    for item in registered:
        row = (
            db.query(Experiment)
            .filter(
                Experiment.policy_id == item.policy_id,
                Experiment.industry == industry,
                Experiment.status.in_(['active', 'running']),
            )
            .order_by(Experiment.created_at.desc())
            .first()
        )
        if row is None:
            if new_experiments >= cap:
                continue
            row = Experiment(
                policy_id=item.policy_id,
                hypothesis=f'Evolved policy {item.policy_id} from {item.parent_policy} improves outcomes for {industry}.',
                experiment_type='strategy_evolution',
                cohort_size=100,
                status='active',
                industry=industry,
            )
            db.add(row)
            db.flush()
            new_experiments += 1
        experiment_ids.append(row.experiment_id)
    return experiment_ids
