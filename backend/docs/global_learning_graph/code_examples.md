# Code Examples (Design Pseudocode)

## 1) Edge upsert payload
~~~json
{
  "source_node_id": "strategy:onpage_internal_linking",
  "target_node_id": "outcome:rank_position_change",
  "edge_type": "improves",
  "confidence": 0.78,
  "support_count": 42,
  "outcome_strength": 1.9,
  "cohort_context": {
    "industry": "home_services",
    "geo": "US",
    "window": "90d"
  },
  "timestamp": "2026-03-05T12:30:00Z",
  "model_version": "policy_engine_v3.4"
}
~~~

## 2) Derive edges from recommendation outcome
~~~python
for outcome_event in outcome_events:
    strategy_node = node_id("strategy", outcome_event.strategy_key)
    outcome_node = node_id("outcome", outcome_event.outcome_key)

    edge_type = "improves" if outcome_event.delta > 0 else "correlates_with"
    edge = build_edge(
        source=strategy_node,
        target=outcome_node,
        edge_type=edge_type,
        confidence=score_confidence(outcome_event),
        support_count=aggregate_support(strategy_node, outcome_node),
        outcome_strength=outcome_event.delta,
        cohort_context=outcome_event.cohort_context,
        timestamp=outcome_event.observed_at,
        model_version=outcome_event.model_version,
    )
    graph_writer.upsert(edge)
~~~

## 3) Query: strategies that improved rankings
~~~python
results = graph_query.find_strategies(
    target_outcome="rank_position_change",
    industry="home_services",
    relation="improves",
    min_confidence=0.60,
    top_k=10,
)
~~~

## 4) Query: similar campaigns
~~~python
similar = graph_query.find_similar_campaigns(
    campaign_id=current_campaign_id,
    feature_weight=0.6,
    pattern_weight=0.4,
    top_k=20,
)
~~~

## 5) Graph-informed digital twin prior
~~~python
priors = graph_query.estimate_strategy_performance(
    strategy_key=candidate_strategy,
    campaign_context=current_context,
)
simulation = twin.simulate(candidate_strategy, priors=priors)
~~~
