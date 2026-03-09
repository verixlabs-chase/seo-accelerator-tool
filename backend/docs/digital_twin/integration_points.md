# Integration Points

## System definition
This document defines Digital Twin integration hooks into existing deterministic intelligence modules.

## Why this component exists
It ensures additive integration without redesigning stable platform components.

## What problem it solves
- Avoids duplicate logic.
- Preserves backward compatibility.
- Defines precise implementation hooks.

## How it integrates with the intelligence engine
- Signal extraction: [signal_assembler.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/signal_assembler.py)
- Feature computation: [feature_store.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/feature_store.py)
- Pattern discovery: [pattern_engine.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/pattern_engine.py)
- Cohort patterns: [cohort_pattern_engine.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/cohort_pattern_engine.py)
- Recommendation generation: [engine.py](/home/verixlabs/SEO Accelerator Tool/backend/app/services/strategy_engine/engine.py)
- Execution scheduling: [recommendation_execution_engine.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/recommendation_execution_engine.py)
- Outcome capture: [outcome_tracker.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/outcome_tracker.py)
- Policy calibration: [policy_update_engine.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/policy_update_engine.py)

## Integration contract
~~~text
recommendation_engine -> twin_simulation -> decision_optimizer -> execution_engine
execution_engine -> outcome_tracker -> policy_update_engine -> simulation calibration
~~~

## Inputs and outputs
- Input: recommendation candidates and current campaign state.
- Output: ranked selected actions with simulation trace.

## Failure modes
- Missing campaign context propagation.
- Invalid recommendation identifiers.
- Out-of-order pipeline calls.

## Example usage
~~~python
candidates = build_campaign_strategy(...).recommendations
simulated = twin_service.simulate(campaign_id, candidates)
selected = optimizer.select(simulated)
~~~

## Future extensibility
- Add simulation preview endpoint for human review.
