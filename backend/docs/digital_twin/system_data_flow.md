# System Data Flow

## System definition
This document defines end-to-end data flow for twin state updates, simulation runs, execution, and learning feedback.

## Why this component exists
A strict flow definition prevents hidden coupling and ensures deterministic orchestration.

## What problem it solves
- Establishes stage ordering.
- Defines data contracts between stages.
- Enables traceable lineage and replay.

## How it integrates with the intelligence engine
It aligns with current intelligence orchestration and event-driven updates.

## Data flow diagram
~~~text
crawl.completed / report.generated / automation.action_executed
                      |
                      v
              signal_assembler
                      |
                      v
            temporal ingestion
                      |
                      v
                feature_store
                      |
                      v
        pattern_engine + cohort_pattern_engine
                      |
                      v
         recommendation candidates generated
                      |
                      v
             DIGITAL TWIN SIMULATION
                      |
                      v
               decision_optimizer
                      |
                      v
      recommendation_execution_engine
                      |
                      v
               outcome_tracker
                      |
                      v
             policy_update_engine
~~~

## Inputs and outputs
- Input: normalized signals, features, patterns, recommendation candidates.
- Output: selected executable actions and feedback artifacts.

## Failure modes
- Event duplication without idempotency guards.
- Out-of-order updates causing stale simulations.
- Partial writes that skip calibration.

## Example usage
A report generation event triggers feature refresh, simulation run, and strategy reselection.

## Future extensibility
- Add stream processor for near-real-time campaign updates.
