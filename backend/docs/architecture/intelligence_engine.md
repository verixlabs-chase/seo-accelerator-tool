# Intelligence Engine

Audit prerequisite: Future system audits must read the architecture documents in `backend/docs/architecture/` before performing code analysis.

## Purpose
The Intelligence Engine is the synchronous campaign runtime that assembles signals, computes features, detects patterns, derives policies, generates recommendations, runs digital twin selection, schedules execution, and records outcomes.

## Runtime pipeline
```text
run_campaign_cycle()
  -> assemble_signals()                         app/intelligence/signal_assembler.py
  -> write_temporal_signals()                   app/intelligence/temporal_ingestion.py
  -> compute_features()                         app/intelligence/feature_store.py
  -> detect_patterns()                          app/intelligence/pattern_engine.py
  -> discover_cohort_patterns()                 app/intelligence/pattern_engine.py
  -> _generate_and_persist_recommendations()    app/intelligence/intelligence_orchestrator.py
       -> derive_policy()/score_policy()/generate_recommendations()
  -> _select_recommendations_via_digital_twin() app/intelligence/intelligence_orchestrator.py
       -> optimize_strategy()                   app/intelligence/digital_twin/strategy_optimizer.py
  -> _schedule_recommendation_executions()      app/intelligence/intelligence_orchestrator.py
       -> schedule_execution()                  app/intelligence/recommendation_execution_engine.py
  -> _execute_scheduled_executions()            app/intelligence/intelligence_orchestrator.py
       -> execute_recommendation()              app/intelligence/recommendation_execution_engine.py
       -> record_execution_outcome()            app/intelligence/outcome_tracker.py
```

## Core modules
- `app/intelligence/intelligence_orchestrator.py`
- `app/intelligence/signal_assembler.py`
- `app/intelligence/feature_store.py`
- `app/intelligence/pattern_engine.py`
- `app/intelligence/policy_engine.py`
- `app/intelligence/contracts/recommendations.py`
- `app/intelligence/recommendation_execution_engine.py`
- `app/intelligence/outcome_tracker.py`

## Data models
- `StrategyRecommendation`
- `RecommendationExecution`
- `RecommendationOutcome`
- `DigitalTwinSimulation`
- `PolicyWeight`
- `CampaignDailyMetric`, `TemporalSignalSnapshot`, `MomentumMetric`

## Event integrations
- `assemble_signals()` publishes `signal.updated`
- `compute_features()` publishes `feature.updated`
- pattern discovery publishes `pattern.discovered`
- execution emits `execution.scheduled`, `execution.started`, `execution.completed`, `execution.failed`, `execution.rolled_back`
- outcomes publish `outcome.recorded` after commit
- `recommendation.outcome_recorded` is emitted for audit log and learning integration

## Safety constraints
- recommendation payloads are validated through `RecommendationPayload`
- scheduling and execution enforce governance policy, safety pause, idempotency key, retry limits, and risk scoring
- outcome publication is post-commit, but execution event emission is still pre-commit

## Scaling risks
- repeated signal and feature recomputation in orchestrator, scheduling, and event integration
- synchronous execution path includes outcome handling and downstream learning triggers
- orchestrator also updates policy weights directly, duplicating later outcome-triggered learning work
