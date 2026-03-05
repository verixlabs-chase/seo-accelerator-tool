# Scaling Strategy

## System definition
Scaling strategy defines workload management and capacity tiers for event driven intelligence operations.

## Purpose
Meet latency and throughput goals at 100 to 5000 campaign scale without full recomputation cycles.

## Capacity tiers
- 100 campaigns
  - one queue per major stage
  - small fixed worker pool
- 500 campaigns
  - stage specific queues
  - tenant aware partitioning
- 1000 campaigns
  - hash sharding by campaign_id
  - autoscaling consumers by queue depth
- 5000 campaigns
  - multi lane priority queues
  - strict backpressure and dead letter analytics

## Inputs
- queue depth and processing rate metrics
- event throughput by type

## Outputs
- worker scaling decisions
- throttling and partition policies

## Data models
- QueueMetrics with queue_name, depth, wait_ms, processed_per_min
- ThroughputPolicy with stage, max_rate, target_latency_ms

## Failure modes
- hot partitions
- noisy tenant spikes
- sustained backlog growth

## Why event driven prevents recomputation explosion
Only impacted campaign stages are recomputed. One crawl completion triggers local signal and feature updates for one campaign instead of full fleet recalculation.

## Scaling considerations
- tenant rate limits
- campaign scoped idempotency
- low priority batching for non critical events

## Example code snippet
    def required_workers(queue_depth):
        if queue_depth < 100:
            return 2
        if queue_depth < 1000:
            return 8
        return 20

## Integration points
- celery worker autoscaling
- intelligence monitoring dashboards

