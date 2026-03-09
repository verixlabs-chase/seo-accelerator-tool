# Decision Optimizer

## System definition
Decision Optimizer chooses the best policy-safe recommendation actions from simulation outputs.

## Why this component exists
Predictions must be converted into deterministic execution choices with governance constraints.

## What problem it solves
- Ranks competing actions.
- Applies confidence and risk filters.
- Produces traceable selection decisions.

## How it integrates with the intelligence engine
It is placed after simulation and before recommendation execution scheduling.

## Optimization formula
~~~text
expected_value = predicted_delta * confidence_score
risk_adjusted_value = expected_value - risk_penalty
~~~

## Inputs
- SimulationResult list
- Governance policy constraints
- Campaign daily execution capacity

## Outputs
- Approved actions
- Deferred actions
- Rejected actions with reason codes

## Pseudocode
~~~python
def optimize_strategy(sim_results, max_actions, min_confidence):
    eligible = [r for r in sim_results if r[confidence] >= min_confidence]
    ranked = sorted(
        eligible,
        key=lambda r: (-r[risk_adjusted_value], -r[confidence], r[action]),
    )
    return ranked[:max_actions]
~~~

## Failure modes
- Empty eligible set
- Missing risk metadata
- Governance config unavailable

## Example usage
~~~python
selected = optimize_strategy(results, max_actions=3, min_confidence=0.6)
~~~

## Future extensibility
- Budget-aware constrained optimization.
- Multi-objective optimization for rank and conversion goals.
