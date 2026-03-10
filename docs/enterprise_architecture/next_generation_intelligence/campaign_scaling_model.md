# Campaign Scaling Model

## Scale targets
- 50,000+ active campaigns.
- Millions of incoming signals per day.
- Thousands of concurrent digital twin simulations.

## Partitioning strategy
- Campaign-sharded processing by stable hash.
- Industry-aware secondary partitioning for transfer learning locality.
- Tenant isolation boundaries for noisy-neighbor control.

## Throughput strategy
- Micro-batch signals by campaign and window.
- Async fan-out from signals to feature and pattern workers.
- Queue depth-aware autoscaling.

## Capacity model
- Baseline workers sized for p50 load.
- Burst workers for p95 spikes.
- Predictive autoscaling using historical event volume and time-of-day patterns.

## SLOs
- Decision freshness: < 5 minutes from signal ingestion to recommendation refresh.
- Simulation queue wait p95: < 60 seconds.
- End-to-end campaign cycle p95: < 3 seconds (distributed pipeline).
