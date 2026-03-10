# Integration With Strategy Evolution

## Integration Diagram
```text
discovered hypotheses
  -> digital twin validation
  -> strategy_experiment_engine
  -> strategy_performance_analyzer
  -> lifecycle manager
```

## Integration Points
- `app/intelligence/strategy_evolution/strategy_experiment_engine.py`
- `app/intelligence/strategy_evolution/strategy_performance_analyzer.py`
- `app/intelligence/strategy_evolution/strategy_lifecycle_manager.py`

## Code Example
```python
hypotheses = generate_strategy_hypotheses(patterns)
experiment_candidates = plan_experiment_candidates(db, hypotheses=hypotheses, campaign_ids=campaign_ids)
```

## Strategy Discovery Example
A discovered anchor-placement strategy enters the same experiment and promotion path as manually defined strategies.

## Experiment Workflow
Hypothesis -> experiment -> observed outcomes -> updated performance score -> promotion or demotion.
