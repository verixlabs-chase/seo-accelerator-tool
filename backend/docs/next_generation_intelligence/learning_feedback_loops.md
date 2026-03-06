# Learning Feedback Loops

## Continuous loop design
~~~text
signals -> features -> patterns -> recommendations
        -> simulations -> execution -> outcomes
        -> graph updates -> rule discovery -> policy updates
        -> better recommendations
~~~

## Loop components
- Outcome attribution service linking actions to effects.
- Graph update service for cross-campaign evidence.
- Causal rule discovery for explainable policy refinement.
- Calibration service for simulation confidence correction.

## Cadence
- Real-time: event capture and graph edge updates.
- Hourly: strategy transfer refresh and risk threshold checks.
- Daily: model retraining + rule validation cycles.

## Quality gates
- Minimum evidence thresholds before policy impact.
- Rollback triggers for negative trend detection.
- Human review mode for low-confidence automation segments.
