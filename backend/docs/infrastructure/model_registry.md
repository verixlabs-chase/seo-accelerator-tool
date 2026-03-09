# Model Registry

The platform now exposes one logical model registry in `app/intelligence/model_registry/model_registry.py`. Digital twin and predictive forecasting modules keep their existing imports, but both are wrappers over the shared persisted registry state stored in `intelligence_model_registry_states`.

Tracked models:

- `rank_prediction_model`
- `traffic_prediction_model`
- `confidence_estimator`
- `forecast_model`
