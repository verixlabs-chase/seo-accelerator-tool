# Digital Twin

Audit prerequisite: Future system audits must read the architecture documents in `backend/docs/architecture/` before performing code analysis.

## Purpose
The Digital Twin scores candidate strategies and selects the highest expected-value recommendation set before execution.

## Runtime pipeline
```text
run_campaign_cycle()
  -> _select_recommendations_via_digital_twin()
     -> DigitalTwinState.from_campaign_data()
     -> optimize_strategy()
        -> simulate_strategy() for each candidate strategy
        -> persist DigitalTwinSimulation rows
        -> mark selected_strategy=True on the winner
```

## Core modules
- `app/intelligence/digital_twin/twin_state_model.py`
- `app/intelligence/digital_twin/strategy_optimizer.py`
- `app/intelligence/digital_twin/strategy_simulation_engine.py`
- `app/intelligence/digital_twin/models/*`

## Data models
- `DigitalTwinSimulation`
- `DigitalTwinState` runtime dataclass
- model-registry-backed predictor parameters

## Event integrations
- no direct bus subscription
- execution outcomes later resolve the selected simulation via `outcome_tracker._resolve_simulation_for_execution()`

## Safety constraints
- simulations are deterministic for a given state and action set
- selection is bounded to the in-memory candidate list produced by the orchestrator
- no direct mutation delivery occurs in the twin layer

## Scaling risks
- one simulation write per candidate strategy
- model inference is synchronous inside the campaign cycle
- state construction recomputes signals and features, increasing duplicate reads
