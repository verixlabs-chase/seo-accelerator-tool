from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.intelligence.evolution.evolution_models import PolicyMutationCandidate, RegisteredPolicyEntry
from app.intelligence.knowledge_graph.update_engine import record_policy_evolution
from app.models.intelligence_model_registry import IntelligenceModelRegistryState
from app.models.policy_weights import PolicyWeight
from app.models.strategy_evolution_log import StrategyEvolutionLog

_POLICY_REGISTRY_NAME = 'policy_registry'


def register_mutated_policies(db: Session, mutations: list[PolicyMutationCandidate]) -> list[RegisteredPolicyEntry]:
    if not mutations:
        return []

    registry = db.get(IntelligenceModelRegistryState, _POLICY_REGISTRY_NAME)
    payload = registry.payload if registry is not None and isinstance(registry.payload, dict) else {'policies': {}}
    policies = payload.setdefault('policies', {})

    registered: list[RegisteredPolicyEntry] = []
    now = datetime.now(UTC).isoformat()
    for mutation in mutations:
        row = _ensure_evolution_log(db, mutation)
        _ = row
        record_policy_evolution(
            db,
            parent_policy=mutation.parent_policy,
            child_policy=mutation.new_policy,
            industry=mutation.industry,
            confidence=mutation.confidence,
            effect_size=mutation.expected_effect,
        )
        policies[mutation.new_policy] = {
            'parent_policy': mutation.parent_policy,
            'mutation_type': mutation.mutation_type,
            'industry': mutation.industry,
            'status': 'experimental',
            'expected_effect': mutation.expected_effect,
            'confidence': mutation.confidence,
            'created_at': now,
        }
        weight = db.get(PolicyWeight, f'policy::{mutation.new_policy}')
        if weight is None:
            weight = PolicyWeight(policy_id=f'policy::{mutation.new_policy}')
            db.add(weight)
        weight.weight = max(0.1, round(0.5 + mutation.expected_effect, 6))
        weight.confidence = mutation.confidence
        weight.sample_size = 0
        weight.last_updated = datetime.now(UTC)
        registered.append(
            RegisteredPolicyEntry(
                policy_id=mutation.new_policy,
                parent_policy=mutation.parent_policy,
                mutation_type=mutation.mutation_type,
                industry=mutation.industry,
                status='experimental',
            )
        )

    if registry is None:
        registry = IntelligenceModelRegistryState(registry_name=_POLICY_REGISTRY_NAME, payload=payload, updated_at=datetime.now(UTC))
        db.add(registry)
    else:
        registry.payload = payload
        registry.updated_at = datetime.now(UTC)
    db.flush()
    return registered


def _ensure_evolution_log(db: Session, mutation: PolicyMutationCandidate) -> StrategyEvolutionLog:
    row = (
        db.query(StrategyEvolutionLog)
        .filter(
            StrategyEvolutionLog.parent_policy == mutation.parent_policy,
            StrategyEvolutionLog.new_policy == mutation.new_policy,
        )
        .first()
    )
    if row is not None:
        return row
    row = StrategyEvolutionLog(
        parent_policy=mutation.parent_policy,
        new_policy=mutation.new_policy,
        mutation_type=mutation.mutation_type,
    )
    db.add(row)
    db.flush()
    return row
