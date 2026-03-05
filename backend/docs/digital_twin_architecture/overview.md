# Campaign Digital Twin Overview

## System definition
Campaign Digital Twin is a deterministic virtual model of a campaign used to predict SEO outcomes before execution.

## Why this component exists
It adds a pre-execution forecasting layer so the intelligence platform can reduce risky actions and prioritize expected-impact actions.

## What problem it solves
- Improves recommendation quality before automation runs.
- Reduces negative outcomes from low-confidence actions.
- Adds simulation traces for audit and replay.

## How it integrates with the intelligence engine
- Inputs from [signal_assembler.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/signal_assembler.py)
- Features from [feature_store.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/feature_store.py)
- Pattern context from [pattern_engine.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/pattern_engine.py) and [cohort_pattern_engine.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/cohort_pattern_engine.py)
- Recommendation candidates from [engine.py](/home/verixlabs/SEO Accelerator Tool/backend/app/services/strategy_engine/engine.py)
- Execution bridge to [recommendation_execution_engine.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/recommendation_execution_engine.py)
- Outcome loop with [outcome_tracker.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/outcome_tracker.py) and [policy_update_engine.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/policy_update_engine.py)

## Design goals
- Fully deterministic decision path.
- Reproducible simulation output for same input.
- Clear contracts for engineers and AI coding agents.
- Safe integration with governance controls.

## Inputs
- Ranking signals
- Content inventory and growth
- Internal link and technical issue graph metrics
- Local search signals
- Campaign KPI and momentum metrics
- Candidate strategy actions

## Outputs
- Predicted rank delta
- Predicted traffic delta
- Confidence score
- Expected value score
- Decision trace for selected recommendations

## Continuous improvement loop
~~~text
Crawl/Rank/Local/KPI Signals
      -> Signal Extraction
      -> Feature Store
      -> Pattern Engines
      -> Recommendation Candidates
      -> DIGITAL TWIN SIMULATION
      -> Decision Optimizer
      -> Execution
      -> Outcomes
      -> Policy Learning
~~~

## Example response
~~~json
{
  predicted_rank_delta: 2.4,
  predicted_traffic_delta: 18.2,
  confidence: 0.71
}
~~~

## Failure modes
- Sparse history lowers confidence.
- Feature drift reduces prediction quality.
- Cohort misclassification biases expected value.

## Example usage
1. Build twin state for campaign.
2. Simulate approved strategy candidates.
3. Rank by risk-adjusted expected value.
4. Execute top actions and compare outcomes.

## Future extensibility
- Multi-action sequence simulation.
- Portfolio-level optimization.
- Counterfactual replay for calibration testing.
