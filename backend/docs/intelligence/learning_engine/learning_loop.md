# Learning Feedback Loop

## Objective
Close the loop from recommendation execution to policy improvement.

## Learning cycle
1. ingest outcomes
2. validate outcome quality
3. aggregate by pattern and recommendation type
4. update effectiveness scores
5. update policy priors and thresholds
6. publish new policy bundle version

## Learning loop diagram

Recommendation executed
      |
      v
Outcome measured
      |
      v
Reward computed
      |
      v
Pattern effectiveness update
      |
      v
Policy bundle update
      |
      v
Next recommendation generation uses new priors

## Update strategy
- small bounded updates per cycle
- minimum sample size requirements
- cooldown windows for policy changes
- rollback support for policy bundle regressions

## Pseudocode

    def run_learning_cycle(cycle_date):
        outcomes = load_new_outcomes(cycle_date)
        valid = filter_quality_outcomes(outcomes)

        perf = aggregate_effectiveness(valid)
        pattern_updates = update_pattern_confidence(perf)
        policy_updates = tune_policy_weights(perf)

        new_bundle = create_policy_bundle(pattern_updates, policy_updates)
        publish_bundle(new_bundle)
        return new_bundle

## Safety rules
- no direct writes to live bundle without validation
- all updates are versioned and replayable
- require holdout checks before activation
