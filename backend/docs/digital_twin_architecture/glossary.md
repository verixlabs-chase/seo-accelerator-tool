# Glossary

## System definition
Canonical terminology for the Campaign Digital Twin architecture.

## Why this component exists
Shared language is required for consistent implementation and operations.

## What problem it solves
- Prevents naming drift across docs, code, APIs, and tests.

## How it integrates with the intelligence engine
Terms map directly to current deterministic intelligence modules.

## Terms
- Campaign Digital Twin: Deterministic virtual model of campaign state used for simulation.
- Twin state: Immutable state snapshot consumed by simulator.
- Simulation scenario: Candidate action set evaluated in twin.
- Prediction model: Deterministic formulas used for delta estimation.
- Expected value: Predicted impact multiplied by confidence, adjusted by risk.
- Decision optimizer: Component selecting top policy-safe strategies.
- Cohort pattern: Cross-campaign recurring evidence pattern.
- Strategy memory: Persisted validated patterns used as scoring multipliers.
- Outcome delta: Before/after metric difference after execution.
- Calibration: Updating deterministic policy inputs from outcomes.
- Governance policy: Safety constraints for execution permissions and caps.
- Circuit breaker: Global pause on unhealthy execution behavior.

## Example usage
Use these terms in API schemas, migration names, and implementation tickets.

## Future extensibility
- Add domain-specific sub-glossaries for local SEO, technical SEO, and content strategy.
