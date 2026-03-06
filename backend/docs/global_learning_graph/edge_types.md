# Edge Types

## improves
Indicates source contributes positive change to target outcome.
- Common examples: strategy -> outcome, pattern -> outcome.
- outcome_strength is generally positive; negative values indicate regression signals.

## correlates_with
Indicates statistically meaningful association without direct causality claim.
- Common examples: feature -> outcome, pattern -> strategy.
- Confidence should account for confounders and cohort consistency.

## causes
Indicates strongest causal claim with stricter evidence thresholds.
- Common examples: strategy -> outcome where controlled evidence exists.

## derived_from
Indicates target was generated from source in pipeline lineage.
- Common examples: pattern -> feature set, outcome -> strategy execution context.

## Required metadata for every edge
- confidence
- support_count
- outcome_strength
- cohort_context
- timestamp
- model_version

## Edge quality thresholds (initial policy)
- improves: confidence >= 0.60 and support_count >= 5.
- correlates_with: confidence >= 0.55 and support_count >= 8.
- causes: confidence >= 0.75 plus causal evidence tag.
- derived_from: deterministic lineage, confidence fixed at 1.0.

Thresholds are policy-controlled and can be recalibrated by governance.
