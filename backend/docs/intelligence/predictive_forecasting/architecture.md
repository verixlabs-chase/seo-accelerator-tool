# Forecasting Architecture

## Components
- Prediction feature builder
- Forecast models (rank, traffic, confidence, risk)
- Prediction engine (online inference)
- Model registry (versioned artifacts + metadata)
- Training pipeline (offline retraining + validation)

## Runtime architecture
~~~text
Strategy Candidate + Campaign + Industry + Graph Evidence
                    -> Feature Builder
                    -> Forecast Ensemble
                    -> Prediction Engine API
                    -> Prioritized Strategy Set
~~~

## Storage and governance
- Model registry stores version, training window, and metrics.
- Prediction logs store input hash, model version, outputs, and latency.
- Promotion gates block weak or drifted models.
