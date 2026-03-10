# Strategy Evolution Engine

Audit prerequisite: Future system audits must read the architecture documents in `backend/docs/architecture/` before performing code analysis.

## Purpose
The new evolution engine reads strong causal policies, generates mutated policy variants, registers them as experimental policies, and opens new experiments automatically.

## Runtime pipeline
```text
strong causal policies
  -> identify_strong_causal_policies()
  -> generate_mutation_candidates()
  -> register_mutated_policies()
     -> write policy_registry payload
     -> upsert policy weight seed
     -> persist StrategyEvolutionLog
  -> _ensure_experiments()
```

## Core modules
- `app/intelligence/evolution/strategy_generator.py`
- `app/intelligence/evolution/policy_mutation_engine.py`
- `app/intelligence/evolution/strategy_evolution_engine.py`
- `app/intelligence/evolution/evolution_models.py`

## Data models
- `StrategyEvolutionLog`
- `IntelligenceModelRegistryState` entry `policy_registry`
- `PolicyWeight`
- `Experiment`

## Event integrations
- current status: implemented and tested, but not yet wired into the live event chain
- intended upstream source is the causal graph
- intended downstream target is the experiment network

## Safety constraints
- mutations are deterministic for known policies:
  - `increase_internal_links -> increase_internal_links_more`
  - `add_location_pages -> add_location_pages_cluster`
- registration is idempotent per `(parent_policy, new_policy)`
- new policies are marked `experimental` in registry state

## Scaling risks
- mutation growth can create unbounded new policy IDs
- `policy_registry` is stored as one JSON payload and is rewritten on update
- experiment fan-out increases with every accepted mutation

## Learning loop
```text
causal edge with positive effect + confidence
  -> strong policy candidate
  -> mutated policy variant
  -> policy_registry status=experimental
  -> new experiment
  -> outcome attribution
  -> new causal edge
```
