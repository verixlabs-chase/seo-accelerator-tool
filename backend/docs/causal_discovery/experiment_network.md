# Experiment Network

## Purpose
The experiment network runs controlled A/B style strategy tests across similar campaigns.

## Workflow Diagram
```text
strategy hypothesis
  -> eligible industry cohort
  -> digital twin screening
  -> experiment candidate list
  -> strategy_evolution.strategy_experiment_engine
  -> execution + flight recorder
```

## Experiment Design
- Cohort by industry and campaign maturity.
- Compare baseline strategy vs discovered strategy.
- Require digital twin expected value and confidence thresholds.
- Feed results into `strategy_performance`, the global graph, and industry priors.

## Code Example
```python
candidates = plan_experiment_candidates(
    db,
    hypotheses=hypotheses,
    campaign_ids=campaign_ids,
)
```

## Strategy Discovery Example
Run `contextual_internal_link_cluster` against 50 HVAC campaigns while retaining a control cohort.

## Experiment Workflow
Screen -> assign cohort -> execute -> record outcomes -> update strategy performance.
