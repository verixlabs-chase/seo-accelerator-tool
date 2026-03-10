# Pattern Discovery Engine

## Purpose
Discover high value repeatable relations between features and outcomes, then expose patterns to policy as scored evidence.

## Pattern discovery modes
1. Deterministic rule learning
- human defined templates over feature thresholds
- easier governance and explainability

2. Statistical learning
- correlation and uplift estimation across cohorts
- confidence adjusted by sample size and stability

## Pattern lifecycle
1. Candidate detection from feature windows.
2. Evidence accumulation from historical outcomes.
3. Validation against holdout periods.
4. Promotion to active pattern registry.
5. Ongoing performance monitoring.

## Pattern data flow
Feature store
   |
   v
Candidate miner
   |
   v
Validation and scoring
   |
   v
Active pattern registry
   |
   v
Recommendation policy engine

## Pseudocode

    def discover_patterns(feature_rows, outcome_rows):
        candidates = []

        for rule in deterministic_templates():
            match_set = apply_rule(rule, feature_rows)
            score = compute_rule_uplift(match_set, outcome_rows)
            if score.sample_size >= minimum_sample_size and score.uplift >= uplift_threshold:
                candidates.append(build_pattern(rule, score))

        for model in statistical_models():
            mined = model.mine(feature_rows, outcome_rows)
            candidates.extend(filter_stable_patterns(mined))

        validated = validate_on_holdout(candidates)
        persist_pattern_versions(validated)
        return validated

## Scoring dimensions
- effect size
- confidence interval width
- sample size
- recency weight
- stability across campaign cohorts

## Governance controls
- block promotion if explainability metadata is missing
- block promotion if pattern confidence below threshold
- require pattern versioning and lineage references
