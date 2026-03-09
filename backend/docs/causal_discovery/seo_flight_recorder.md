# SEO Flight Recorder

## Purpose
The flight recorder provides mutation-level evidence for causal learning.

## Captured Fields
- `execution_id`
- `campaign_id`
- `industry_id`
- `page_url`
- `mutation_type`
- `mutation_parameters`
- `rank_before`
- `rank_after`
- `traffic_before`
- `traffic_after`
- `recorded_at`

## Data Flow Diagram
```text
execution_mutation + recommendation_outcome
  -> record_seo_flight()
  -> seo_mutation_outcomes
  -> causal discovery queries
```

## Code Example
```python
record_seo_flight(db, execution_id=execution_id, industry_id='hvac')
```

## Strategy Discovery Example
The recorder can distinguish `insert_internal_link` mutations with `placement=first_paragraph` from footer links.

## Experiment Workflow
Recorded outcomes become the post-experiment evidence source for strategy evolution and graph updates.
