# Intelligence System

Audit prerequisite: Future system audits must read the architecture documents in `backend/docs/architecture/` before performing code analysis.

## System architecture diagram
```text
run_campaign_cycle()
  -> signals            signal_assembler.py
  -> temporal store     temporal_ingestion.py
  -> features           feature_store.py
  -> patterns           pattern_engine.py
  -> policies           policy_engine.py
  -> recommendations    intelligence_orchestrator.py
  -> digital twin       digital_twin/*
  -> execution          recommendation_execution_engine.py
  -> outcomes           outcome_tracker.py
     -> portfolio       portfolio/portfolio_engine.py
     -> experiments     experiments/experiment_engine.py
     -> post-commit events
        -> OUTCOME_RECORDED     policy_learning_processor.py
        -> EXPERIMENT_COMPLETED causal_learning_processor.py
```

## Learning loop diagram
```text
execution completed
  -> outcome recorded
  -> policy performance updated
  -> explore assignments enter experiments
  -> experiment outcomes attributed
  -> causal edges updated
  -> causal preferences bias portfolio
  -> future strategies selected
```

## Policy lifecycle
```text
pattern match
  -> policy derivation
  -> recommendation generation
  -> digital twin selection
  -> execution scheduling
  -> execution completed/failed/rolled_back
  -> outcome tracked
  -> policy weight updated
```

## Experiment lifecycle
```text
explore allocation
  -> ensure_experiment_for_policy
  -> deterministic control/treatment assignment
  -> experiment outcome persistence
  -> effect analysis
  -> experiment.completed event
```

## Causal discovery lifecycle
```text
experiment.completed
  -> validate payload
  -> upsert weighted causal edge
  -> query positive/high-confidence policies
  -> feed portfolio ranking
  -> feed strategy evolution candidates
```

## Strategy evolution lifecycle
```text
strong causal policy
  -> generate mutation
  -> register experimental policy
  -> seed policy weight
  -> launch strategy_evolution experiment
```

## Runtime reality check
- The live pipeline reaches portfolio and experiments only through outcome tracking.
- `EXPERIMENT_COMPLETED` is runtime-integrated.
- The new `app/intelligence/evolution/` package is implemented but not yet invoked from the live event chain.
- `OUTCOME_RECORDED` still triggers the older `strategy_evolution` and `network_learning` path through `policy_learning_processor.py`.

## Safety constraints
- recommendation payload contract is enforced
- outcome publication is post-commit
- execution event emission still has pre-commit paths and should be treated as non-atomic

## Scaling risks
- duplicate signal/feature recomputation across orchestrator, execution scheduling, and learning integration
- synchronous outcome-triggered model training and network learning
- graph, experiment, and mutation cardinality can all grow without lifecycle pruning
