# Predictive Strategy Forecasting Overview

## Purpose
Predictive Strategy Forecasting estimates expected SEO outcomes before simulation or execution so the platform can prioritize high-impact, low-risk strategies earlier in the decision path.

## Forecast outputs
- Expected rank improvement (`expected_rank_delta`)
- Expected traffic change (`expected_traffic_delta`)
- Confidence score (`confidence_score`)
- Risk score (`risk_score`)

## Position in pipeline
~~~text
signals -> features -> patterns -> strategy candidates
        -> PREDICTIVE STRATEGY FORECASTING
        -> digital twin simulation -> execution -> outcomes
~~~
