# Performance and Scaling

## Target scale
- 50,000+ active campaigns.
- Millions of signals/day.
- 100,000+ simulations/day.
- Thousands of concurrent simulation tasks.

## Capacity strategy
- Horizontal worker scaling across all pipeline stages.
- Queue partitioning by campaign hash and priority tier.
- Dedicated pools for simulation-heavy workloads.

## Latency and throughput targets
- Signal-to-feature p95: < 30s.
- Feature-to-recommendation p95: < 60s.
- Simulation queue wait p95: < 60s.
- End-to-end refresh p95: < 5 minutes.

## Bottleneck management
- Autoscale on queue lag and event throughput.
- Cache hot graph queries and repeated simulations.
- Move heavy learning jobs to asynchronous offline windows.

## Observability SLOs
- Queue lag by topic/partition.
- Worker error rate and retry volume.
- Model prediction error and calibration drift.
- Strategy transfer uplift vs baseline.
