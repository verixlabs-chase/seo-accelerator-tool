# Causal Rule Engine

## Purpose
Extract interpretable causal rules from observed campaign outcomes to improve strategy selection and explainability.

## Rule representation
~~~text
IF <context + feature + intervention conditions>
THEN expected_rank_delta = X, probability = P, confidence = C
~~~

## Rule discovery
- Generate candidate rules from frequent condition sets.
- Estimate treatment effect with cohort-matched comparisons.
- Filter by minimum support and stability over time windows.

## Confidence scoring
- Inputs: effect size, support count, variance, cohort consistency, recency.
- Confidence score bounded [0, 1] with decay for stale evidence.

## Lifecycle management
- States: proposed -> validated -> active -> deprecated.
- Automatic demotion on sustained performance regression.
- Lineage links from rule to source events and outcomes.

## Integration with strategy generation
- Rules become priors in recommendation ranking.
- High-confidence causal rules can elevate strategy candidates.
- Conflicting rules are resolved by confidence and recency policy.
