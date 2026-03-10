# Outcome Tracking System

## Purpose
Measure recommendation effectiveness and produce learning labels.

## Outcome tracking entities
- recommendation execution event
- baseline metric snapshot
- evaluation metric snapshot
- delta calculations
- reward signal

## Evaluation workflow
1. Capture baseline window before execution.
2. Capture execution metadata and action completion date.
3. Capture evaluation window metrics after execution.
4. Compute metric deltas and normalized reward.
5. Persist recommendation outcome record.

## Delta framework
- absolute delta: current minus baseline
- relative delta: absolute delta divided by baseline
- directionality aware scoring by metric objective

## Reward composition example
reward equals weighted blend of:
- ctr_delta_weighted
- avg_position_delta_weighted
- conversion_delta_weighted
- technical_issue_reduction_weighted

## Pseudocode

    def evaluate_recommendation_outcome(recommendation_id):
        rec = get_recommendation(recommendation_id)
        baseline = load_baseline_metrics(rec.campaign_id, rec.baseline_window)
        evaluation = load_evaluation_metrics(rec.campaign_id, rec.evaluation_window)

        deltas = compute_metric_deltas(baseline, evaluation)
        reward = compute_reward(deltas, reward_weights())

        persist_outcome(recommendation_id, baseline, evaluation, deltas, reward)
        return reward

## Data quality checks
- ensure enough observations in evaluation window
- handle seasonality and known campaign freezes
- tag outcomes as partial when confidence is low

## Integration points
- recommendation records from app/models/intelligence.py
- KPI source from app/models/campaign_daily_metric.py
- automation execution context from app/models/strategy_automation_event.py
