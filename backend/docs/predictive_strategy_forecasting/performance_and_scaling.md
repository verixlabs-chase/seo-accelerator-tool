# Performance and Scaling

## Scale targets
- 50,000+ active campaigns
- 100,000+ daily strategy forecasts
- Forecast API p95 under 100ms

## Scaling strategy
- Stateless inference workers with autoscaling
- Hot model caching in memory
- Batch candidate inference per campaign cycle
- Async prediction logging path

## Reliability
- Fallback to last-known-good model version
- Circuit breaker on forecast-serving error spikes
