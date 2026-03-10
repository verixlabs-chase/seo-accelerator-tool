# Data Models for Learning

## Model set
Proposed new models:
- seo_signal
- feature_row
- strategy_pattern
- pattern_evidence
- recommendation_outcome
- strategy_effectiveness
- policy_bundle
- learning_feedback_event

## seo_signal
Purpose: canonical extracted signal facts.

Fields:
- id
- tenant_id
- campaign_id
- signal_type
- metric_name
- metric_value
- observed_at
- confidence
- source
- version_hash

Example:

    {
      id: sig_001,
      tenant_id: t_001,
      campaign_id: cmp_001,
      signal_type: rank,
      metric_name: avg_position,
      metric_value: 8.2,
      observed_at: 2026-03-05T00:00:00Z,
      confidence: 0.91,
      source: signal_extractor_rank_v1,
      version_hash: h1
    }

## feature_row
Purpose: reusable feature facts.

Fields:
- id
- tenant_id
- campaign_id
- feature_name
- feature_value
- window_start
- window_end
- feature_version
- source_signal_versions
- computed_at

## strategy_pattern
Purpose: active pattern definitions and current confidence.

Fields:
- id
- pattern_key
- category
- expression
- confidence
- support_count
- uplift_score
- status
- version
- created_at

## pattern_evidence
Purpose: immutable evidence backing each pattern version.

Fields:
- id
- pattern_id
- campaign_id
- feature_snapshot
- outcome_snapshot
- observed_window_start
- observed_window_end
- evidence_hash

## recommendation_outcome
Purpose: link recommendation execution to measured effect.

Fields:
- id
- recommendation_id
- campaign_id
- baseline_window_start
- baseline_window_end
- evaluation_window_start
- evaluation_window_end
- metric_deltas
- reward_score
- confidence
- evaluated_at

## strategy_effectiveness
Purpose: aggregate recommendation and pattern performance statistics.

Fields:
- id
- scope_key
- scope_type
- samples
- mean_reward
- reward_stddev
- win_rate
- updated_at

## policy_bundle
Purpose: versioned policy weights and thresholds.

Fields:
- id
- version
- status
- weights_json
- thresholds_json
- created_at
- activated_at

## learning_feedback_event
Purpose: auditable record of each learning update.

Fields:
- id
- cycle_date
- source_outcome_count
- updated_patterns
- updated_policy_bundle
- validation_status
- created_at

## Relationship sketch
recommendation_outcome references strategy recommendation id
pattern_evidence references strategy_pattern id
strategy_effectiveness aggregates across recommendation_outcome and strategy_pattern
policy_bundle versions consumed by recommendation engine
