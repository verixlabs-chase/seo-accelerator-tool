# Distributed Event Architecture

## Event model
- Immutable event envelopes with event_id, event_type, campaign_id, occurred_at, ersion, payload.
- Topic-per-domain partitioning for throughput and isolation.
- Backward-compatible schema evolution via versioned payload contracts.

## Processing model
- At-least-once delivery with idempotent handlers.
- Consumer groups per worker role.
- Dead-letter queues per topic for poison messages.

## Worker orchestration
- Stateless workers deployed in autoscaled pools.
- Lease-based work claiming for batch tasks.
- Priority queues for high-impact campaigns and retries.

## Failure recovery
- Retry with exponential backoff + jitter.
- Circuit open after repeated downstream failures.
- Replay pipeline from durable event log for data repair.

## Idempotency strategy
- Idempotency key: event_id + handler_version.
- State writes use upsert/compare-and-swap semantics.
- Duplicate events are acknowledged without side effects.
