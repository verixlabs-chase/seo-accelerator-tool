# Simulation Engine

## System definition
Simulation Engine computes deterministic forecast metrics for candidate strategy actions against a DigitalTwinState.

## Why this component exists
It provides a controlled pre-execution stage to estimate outcomes before automation commits changes.

## What problem it solves
- Allows action ranking by expected impact.
- Reduces execution of low-confidence recommendations.
- Produces deterministic simulation artifacts for audit.

## How it integrates with the intelligence engine
It consumes recommendation candidates from strategy generation and returns scored candidates to the decision optimizer.

## Design goals
- Side-effect free simulation.
- Deterministic output for identical state and action.
- Stable output schema.

## Core functions
~~~python
def simulate_strategy(state: DigitalTwinState, action: str) -> dict: ...
def predict_rank_delta(state: DigitalTwinState, action: str) -> float: ...
def predict_traffic_delta(state: DigitalTwinState, rank_delta: float) -> float: ...
~~~

## Pseudocode
~~~python
def simulate_strategy(state, action):
    rank_delta = predict_rank_delta(state, action)
    traffic_delta = predict_traffic_delta(state, rank_delta)
    confidence = compute_confidence(state, action)
    expected_value = traffic_delta * confidence
    return {
        action: action,
        predicted_rank_delta: round(rank_delta, 4),
        predicted_traffic_delta: round(traffic_delta, 4),
        confidence: round(confidence, 4),
        expected_value: round(expected_value, 4),
    }
~~~

## Inputs and outputs
- Input: twin state, action type, policy context.
- Output: prediction payload with confidence and expected value.

## Failure modes
- Missing required features.
- Unknown action type.
- Invalid confidence range.

## Example usage
~~~python
result = simulate_strategy(state, improve_internal_links)
~~~

## Future extensibility
- Bundle simulation for action sequences.
- Segment-specific coefficient profiles.
