# Data Flow

## End-to-end flow
~~~text
PATTERN_DISCOVERED / SIMULATION_COMPLETED / OUTCOME_RECORDED
  -> feature joins + industry priors + graph priors
  -> forecasting inference
  -> recommendation ranking and simulation pre-filter
  -> execution + outcomes
  -> training data refresh
~~~

## Logging and lineage
Each prediction record carries model version, feature hash, campaign, strategy, and outputs.
