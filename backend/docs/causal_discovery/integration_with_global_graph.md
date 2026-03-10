# Integration With Global Learning Graph

## Graph Edge Model
- `strategy -> outcome (causes)`
- `pattern -> strategy (derived_from)`
- `campaign -> pattern (derived_from)`

## Metadata Requirements
- `confidence`
- `support_count`
- `industry_context`
- `timestamp`
- `model_version`

## Diagram
```text
flight recorder -> causal analyzer -> graph evidence edges
pattern discovery -> derived strategy edges
experiment results -> stronger causal outcome edges
```

## Code Example
```python
pipeline.update_from_outcome({
    'campaign_id': campaign_id,
    'strategy_id': strategy_id,
    'delta': observed_delta,
    'confidence': confidence,
    'is_causal': True,
    'industry': 'hvac',
})
```

## Strategy Discovery Example
`internal_link_cluster_first_paragraph` can emit a `derived_from` edge from its source pattern and a `causes` edge to observed rank improvement.

## Experiment Workflow
Confirmed experiments strengthen graph edges; weak experiments degrade confidence and support future demotion.
