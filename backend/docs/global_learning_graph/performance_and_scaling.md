# Performance and Scaling

## Performance objective
Support low-latency query paths for active campaign inference while processing continuous cross-campaign updates.

## Expected workload (design assumptions)
- Campaign count grows continuously across industries.
- Edge volume grows faster than node volume.
- Query traffic spikes during recommendation and simulation windows.

## Scaling strategy
- Separate write and read paths.
- Batch and micro-batch update ingestion.
- Index by node_type, edge_type, industry, outcome, and recency.
- Maintain materialized top-K strategy views per industry/cohort.

## Latency and throughput targets
- Update pipeline end-to-end lag <= 5 minutes for standard batches.
- Query P50 <= 40 ms, P95 <= 120 ms for top-K retrieval.
- Support concurrent campaign recommendation workloads without contention.

## Storage and retention
- Keep full edge history for audit.
- Maintain hot recent window for low-latency queries.
- Archive cold history while retaining replay capability.

## Reliability
- Idempotent writes and retry-safe ingestion.
- Backpressure handling for burst events.
- Graceful degradation to campaign-local intelligence when graph unavailable.

## Observability
- Pipeline lag dashboards.
- Query latency/timeout dashboards.
- Edge growth and cardinality tracking.
- Cache hit rate for hot retrievals.
