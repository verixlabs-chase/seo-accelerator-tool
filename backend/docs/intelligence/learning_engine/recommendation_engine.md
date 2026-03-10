# Recommendation Policy Engine

## Purpose
Generate ranked recommendations using active patterns, feature values, risk controls, and policy bundle weights.

## Inputs
- campaign feature vector
- active pattern registry
- policy bundle weights and thresholds
- campaign phase and constraints
- prior recommendation effectiveness history

## Core outputs
- recommendation list
- priority score
- confidence score
- risk score
- evidence references

## Decision stages
1. Pattern matching.
2. Candidate recommendation generation.
3. Priority and impact scoring.
4. Confidence calibration with historical outcomes.
5. Risk scoring and gating.
6. Final ranking and payload emission.

## Priority scoring model
priority_score can be composed from:
- impact_weight
- signal_magnitude
- confidence_score
- recency_adjustment
- strategic_phase_modifier

## Pseudocode

    def generate_recommendations(campaign_id, window):
        features = load_latest_features(campaign_id, window)
        patterns = load_active_patterns()
        policy = load_policy_bundle()

        candidates = materialize_candidates(features, patterns)

        for c in candidates:
            c.priority_score = score_priority(c, policy)
            c.confidence_score = calibrate_confidence(c, policy)
            c.risk_score = compute_risk(c, policy)

        gated = [c for c in candidates if pass_risk_gates(c, policy)]
        ranked = sort_by_priority(gated)
        return build_payload(ranked, campaign_id, policy.version)

## Example recommendation payload

    {
      recommendation_id: rec_001,
      campaign_id: cmp_001,
      recommendation_type: internal_linking_repair,
      priority_score: 0.82,
      confidence_score: 0.77,
      risk_tier: 2,
      rationale: ranking velocity is declining and internal link ratio is below threshold,
      evidence: [pattern_12, feature_ranking_velocity_14d, feature_internal_link_ratio],
      policy_bundle_version: policy_v2026_03_01
    }

## Integration with current stack
- existing recommendation lifecycle model in app/models/intelligence.py
- existing transitions in app/services/intelligence_service.py
- strategy output schemas in app/services/strategy_engine/schemas.py
