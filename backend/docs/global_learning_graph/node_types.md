# Node Types

## campaign
Represents a managed SEO campaign instance.
- Key attributes: campaign_id, start_date, market, channel_mix, lifecycle_stage.
- Example role: source context for observed features, patterns, strategies, and outcomes.

## industry
Represents a normalized business domain cluster.
- Key attributes: industry_code, taxonomy_path, volatility_profile.
- Example role: transfer boundary for strategy relevance.

## feature
Represents engineered campaign signals used by pattern, recommendation, and simulation systems.
- Key attributes: feature_key, feature_family, value_distribution, freshness.
- Example role: links campaign state to patterns and strategies.

## pattern
Represents detected recurring behavior signature.
- Key attributes: pattern_key, detection_method, significance, validity_window.
- Example role: explains when a strategy tends to work.

## strategy
Represents an abstract intervention approach.
- Key attributes: strategy_key, objective_type, risk_profile.
- Example role: reused across campaigns and industries.

## outcome
Represents observed post-execution result at defined horizon.
- Key attributes: outcome_key, horizon_days, delta_value, confidence_band.
- Example role: closes learning loop for causal and impact updates.
