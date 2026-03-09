# Code Examples

## 1) Causal rule discovery (Python-style)
~~~python
for cohort in cohorts:
    candidates = rule_miner.generate_candidates(cohort.events)
    for rule in candidates:
        effect = estimator.estimate_treatment_effect(rule, cohort.events)
        confidence = scorer.score(effect_size=effect.delta, support=effect.support, variance=effect.variance)
        if confidence >= 0.7 and effect.support >= 30:
            rule_store.upsert(rule=rule, effect=effect, confidence=confidence)
~~~

## 2) Strategy transfer query
~~~python
strategies = transfer_engine.get_top_strategies(
    campaign_id=campaign_id,
    industry=industry,
    features=current_features,
    patterns=active_patterns,
    top_k=10,
)
~~~

## 3) Predictive simulation usage
~~~python
scenarios = simulator.build_scenarios(campaign_context, strategies)
predictions = simulator.run_batch(scenarios)
ranked = optimizer.rank(predictions, risk_profile=campaign_risk_profile)
selected = ranked[:3]
~~~

## 4) Distributed event processing
~~~python
@consumer(topic="outcome.recorded", group="graph-updater")
def handle_outcome(event):
    if idempotency_store.seen(event.id):
        return
    graph_pipeline.update_from_outcome(event.payload)
    idempotency_store.mark_seen(event.id)
~~~
