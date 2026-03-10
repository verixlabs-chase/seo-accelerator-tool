# Strategy Discovery Engine

## Architecture Diagram
```text
causal summaries
  -> strategy pattern discovery
  -> strategy hypothesis engine
  -> digital twin validation
  -> strategy evolution experiment engine
```

## Pattern Classes
- internal link clusters outperform single links
- schema plus internal linking combinations
- first paragraph anchor placement effects

## Code Example
```python
patterns = discover_strategy_patterns(db)
hypotheses = generate_strategy_hypotheses(patterns)
```

## Strategy Discovery Example
```json
{
  "strategy_id": "contextual_internal_link_cluster",
  "mutation_pattern": {
    "mutation_types": ["insert_internal_link"],
    "minimum_links_per_page": 3
  }
}
```

## Experiment Workflow
Patterns with strong support become hypotheses, then simulations decide whether they are eligible for controlled rollout.
