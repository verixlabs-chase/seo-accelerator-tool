# Strategy Evolution Engine

The strategy evolution engine turns historical execution outcomes into automatic strategy lifecycle updates. It sits after policy learning and model retraining, then analyzes which recommendation strategies consistently win, which degrade, and which should be explored through controlled variants.

Modules:

- `strategy_performance_analyzer.py`
- `strategy_mutation_engine.py`
- `strategy_lifecycle_manager.py`
- `strategy_experiment_engine.py`

Persistence:

- `strategy_performance`
- `strategy_experiments`
