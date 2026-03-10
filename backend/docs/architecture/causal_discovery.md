# Causal Discovery

Audit prerequisite: Future system audits must read the architecture documents in `backend/docs/architecture/` before performing code analysis.

## Purpose
The causal layer converts completed experiment results into persistent weighted edges and exposes policy preference queries for downstream allocation and strategy evolution.

## Runtime pipeline
```text
experiment.completed event
  -> causal_learning_processor.process()
     -> learn_from_experiment_completed()
        -> upsert_causal_edge(weighted average by sample size)

portfolio selection
  -> get_policy_preference_map(industry)
strategy evolution
  -> identify_strong_causal_policies()
```

## Core modules
- `app/intelligence/causal/causal_learning_engine.py`
- `app/intelligence/causal/causal_graph.py`
- `app/intelligence/causal/causal_query_engine.py`
- `app/intelligence/event_processors/causal_learning_processor.py`

## Data models
- `CausalEdge`
- runtime `ExperimentCompletedPayload`, `CausalEdgeSnapshot`, `CausalPolicyPreference`

## Event integrations
- subscriber registration happens in `app/events/subscriber_registry.py`
- source event: `experiment.completed`
- main consumer: `causal_learning_processor`

## Safety constraints
- event payload is validated through `ExperimentCompletedPayload`
- edge aggregation is weighted by `sample_size`
- duplicate identity is collapsed by `(source_node, target_node, policy_id, industry)`

## Scaling risks
- current graph semantics are narrow: most runtime edges are `industry::<industry> -> outcome::success`
- query ordering is confidence/effect driven but still synchronous on hot paths
- causal graph is not yet connected to the older global graph or network learning stores
