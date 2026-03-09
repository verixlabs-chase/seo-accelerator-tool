# Performance and Scaling

## System definition
Defines performance targets and scaling strategy for the Digital Twin subsystem.

## Why this component exists
Simulation introduces additional compute and data reads that must remain bounded across campaign volume.

## What problem it solves
- Keeps orchestration cycles predictable.
- Prevents simulation bottlenecks at scale.

## How it integrates with the intelligence engine
Runs within orchestrated campaign cycles and scheduled background tasks.

## Targets
- simulation latency p95 less than 200ms per recommendation
- campaign twin cycle p95 less than 5s
- deterministic parity across worker replicas

## Inputs and outputs
- Input: campaign batches, state snapshots, recommendation sets.
- Output: simulation decisions under SLO thresholds.

## Scaling strategy
- Batch hydrate features per campaign.
- Reuse immutable state snapshots within cycle.
- Partition work by campaign id.
- Keep deterministic ordering for tie-breaks.

## Failure modes
- Queue saturation from burst events.
- Cohort aggregation scans causing DB contention.
- Oversized trace payloads increasing storage and latency.

## Example usage
~~~python
for campaign_id in sorted(active_campaign_ids):
    run_campaign_cycle(campaign_id)
~~~

## Future extensibility
- Dedicated simulation workers.
- Read replicas for heavy analytics queries.
