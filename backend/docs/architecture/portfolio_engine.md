# Portfolio Engine

Audit prerequisite: Future system audits must read the architecture documents in `backend/docs/architecture/` before performing code analysis.

## Purpose
The portfolio engine updates cross-campaign policy performance after each outcome, biases allocation with causal evidence, and assigns exploratory policies into experiments.

## Runtime pipeline
```text
record_outcome()
  -> run_portfolio_cycle()
     -> update_policy_performance()
     -> query top PolicyPerformance rows for industry (limit 50)
     -> get_policy_preference_map() from causal graph
     -> allocate_strategies() with 70/30 exploit/explore split
     -> apply_experiment_assignments()
```

## Core modules
- `app/intelligence/portfolio/portfolio_engine.py`
- `app/intelligence/portfolio/policy_performance.py`
- `app/intelligence/portfolio/strategy_allocator.py`
- `app/intelligence/portfolio/portfolio_models.py`
- `app/intelligence/causal/causal_query_engine.py`
- `app/intelligence/experiments/experiment_engine.py`

## Data models
- `PolicyPerformance`
- `RecommendationOutcome`
- runtime `PolicyPerformanceSnapshot`, `PolicyAllocation`, `PortfolioAllocationResult`

## Event integrations
- no direct subscriber
- invoked from `record_outcome()` before commit
- exploratory allocations feed the experiment network through `apply_experiment_assignments()`

## Safety constraints
- portfolio DB writes happen in the same session as outcome persistence
- industry query is bounded to 50 rows
- no external event is published until the main outcome transaction commits

## Scaling risks
- still performs one synchronous cross-campaign industry query per outcome
- allocations are transient; current assignments are not persisted as first-class state
- causal preference lookup is another synchronous query in the same hot path
