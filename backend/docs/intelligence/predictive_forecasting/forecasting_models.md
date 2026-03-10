# Forecasting Models

## Rank delta model
Predicts expected change in rank for a strategy in campaign + industry context.

## Traffic delta model
Predicts expected traffic movement from rank change and traffic elasticity features.

## Confidence model
Estimates reliability using support, variance, cohort fit, and recency.

## Risk model
Estimates downside probability and severity for governance gating.

## Ensemble scoring
- `expected_value = expected_rank_delta * confidence_score`
- `risk_adjusted_value = expected_value - (risk_score * downside_factor)`
