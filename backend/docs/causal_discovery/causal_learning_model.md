# Causal Learning Model

## Core Metrics
- `support_count`: number of mutation outcomes for a mutation type and industry.
- `average_rank_delta`: mean of `rank_after - rank_before`.
- `variance`: population variance over rank deltas.
- `confidence_score`: combined score from support, consistency, variance, and outlier rate.

## Learning Diagram
```text
mutation outcomes
  -> grouped by mutation_type + industry
  -> support / variance / consistency
  -> causal confidence
  -> positive, neutral, or negative strategy evidence
```

## Statistical Rules
- Consistent positive outcome: average rank delta is negative and positive consistency remains high.
- Outlier mutation: rank delta sits beyond two standard deviations of the group mean.
- Negative strategy: average rank delta is positive and positive consistency is weak.

## Code Example
```python
summary = summarize_mutation_causality(db, target_industry_id='legal')
```

## Strategy Discovery Example
If `add_schema_markup` improves rankings in most outcomes with low variance, it becomes strong causal evidence.

## Experiment Workflow
Only summaries above minimum support and confidence move into pattern discovery.
