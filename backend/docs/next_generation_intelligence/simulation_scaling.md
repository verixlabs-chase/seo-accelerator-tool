# Simulation Scaling

## Goals
Support 100k+ daily simulations with low queue latency and strong prediction calibration.

## Execution model
- Parallel simulation workers with campaign-level sharding.
- Batch simulation of strategy candidates per campaign cycle.
- Priority lanes for high-value and time-sensitive campaigns.

## Performance optimization
- Scenario deduplication by normalized context signature.
- Simulation result caching with TTL and model-version keying.
- Vectorized inference for batch model scoring.

## Calibration
- Post-outcome calibration job updates confidence parameters.
- Cohort-level calibration tables applied at inference time.
- Drift-triggered recalibration for unstable cohorts.

## Reliability
- Retry-safe simulation tasks with deterministic seeds.
- Partial result handling for large candidate sets.
- Graceful degradation to heuristic ranking when simulator backlog exceeds threshold.
