# Code Examples

## 1) Forecast inference
~~~python
forecast = forecasting_engine.predict(
    campaign_id=campaign_id,
    strategy_id=strategy_id,
    industry_id=industry_id,
    features=feature_vector,
)
~~~

## 2) Strategy transfer ranking
~~~python
candidates = transfer_engine.get_graph_candidates(campaign_id, industry_id)
scored = [(c, forecasting_engine.predict(campaign_id, c.strategy_id, industry_id, c.features)) for c in candidates]
ranked = sorted(scored, key=lambda item: item[1]["confidence_score"] * item[1]["expected_rank_delta"], reverse=True)
~~~

## 3) Simulation pre-filter
~~~python
prefiltered = [item for item in ranked if item[1]["risk_score"] <= 0.6]
simulation_results = twin.run_batch(prefiltered)
~~~

## 4) Training entry
~~~python
report = training_pipeline.run(
    from_date="2026-01-01",
    to_date="2026-03-01",
    include_industry_profiles=True,
    include_graph_features=True,
)
~~~
