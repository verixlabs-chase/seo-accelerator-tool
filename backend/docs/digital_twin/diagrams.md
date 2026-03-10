# Diagrams

## System definition
ASCII diagram catalog for Campaign Digital Twin architecture.

## Why this component exists
Provides a single visual reference for engineers, architects, and AI coding agents.

## What problem it solves
- Avoids inconsistent architecture representations across documents.

## How it integrates with the intelligence engine
Each diagram reflects deterministic modules currently present in the intelligence pipeline.

## 1) Full intelligence engine pipeline
~~~text
signals
  -> features
  -> patterns
  -> cohort learning
  -> recommendations
  -> DIGITAL TWIN SIMULATION
  -> execution
  -> outcomes
  -> policy learning
~~~

## 2) Digital twin system architecture
~~~text
Campaign Data
  -> Feature Store
  -> Twin Model
  -> Simulation Engine
  -> Strategy Optimizer
~~~

## 3) Data flow
~~~text
crawl signals + ranking signals + GBP signals + content signals
                      |
                      v
               twin state update
                      |
                      v
                simulation runs
                      |
                      v
             optimizer decisions
                      |
                      v
              execution + outcomes
                      |
                      v
               policy calibration
~~~

## 4) Integration sequence
~~~text
signal_assembler -> feature_store -> pattern_engine -> cohort_pattern_engine
recommendation_engine -> twin_simulation -> decision_optimizer -> recommendation_execution_engine
outcome_tracker -> policy_update_engine
~~~

## Failure modes
- Diagram drift if implementation changes are not documented.

## Future extensibility
- Add deployment topology diagrams when runtime components are implemented.
