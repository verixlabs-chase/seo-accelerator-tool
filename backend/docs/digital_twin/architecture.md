# Campaign Digital Twin Architecture

## System definition
This architecture defines deterministic components, contracts, and stage boundaries for pre-execution SEO strategy simulation.

## Why this component exists
Without an explicit architecture, simulation logic drifts into recommendation and execution layers and becomes hard to validate.

## What problem it solves
- Separates simulation from recommendation generation.
- Adds deterministic scoring between recommendation and execution.
- Preserves auditability and replayability.

## How it integrates with the intelligence engine
The twin layer is inserted between strategy recommendation generation and execution scheduling.

## Full architecture
~~~text
+------------------+    +------------------+    +------------------+
| Signal Assembler | -> | Feature Store    | -> | Pattern Engines  |
+------------------+    +------------------+    +------------------+
          \                    |                          /
           \-------------------+-------------------------/
                               v
                    +------------------------+
                    | Digital Twin State     |
                    +------------------------+
                               |
                               v
                    +------------------------+
                    | Simulation Engine      |
                    +------------------------+
                               |
                               v
                    +------------------------+
                    | Decision Optimizer     |
                    +------------------------+
                               |
                               v
                    +------------------------+
                    | Governance Safety Gate |
                    +------------------------+
                               |
                               v
                    +------------------------+
                    | Execution Engine       |
                    +------------------------+
                               |
                               v
                    +------------------------+
                    | Outcome + Policy Learn |
                    +------------------------+
~~~

## Data models
- DigitalTwinState
- SimulationScenario
- SimulationResult
- OptimizationDecision
- PredictionCalibrationRecord

## Inputs and outputs
- Input: campaign signals, features, pattern context, candidate recommendations.
- Output: selected strategy actions with deterministic ranking trace.

## Failure modes
- Missing required features for specific execution type.
- Unsupported action mapping in simulator.
- Governance blocks all available actions.

## Example usage
~~~text
selected_actions = optimizer.select(simulator.run_batch(twin_state, candidates))
~~~

## Future extensibility
- Split simulator into dedicated service if throughput grows.
- Add replay API for historical cycle validation.
