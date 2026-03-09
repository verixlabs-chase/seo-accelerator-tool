# Event Bus Design

## System definition
The event bus is the internal transport contract for deterministic intelligence events.

## Purpose
Decouple producers and consumers while preserving schema stability, replayability, and idempotent processing.

## Event schema
Required fields:
- event_id
- event_type
- tenant_id
- campaign_id
- occurred_at
- idempotency_key
- deterministic_hash
- payload
- version

## Event publisher rules
- emit only after source transaction commit
- include stable entity identifiers
- include schema version
- publish complete payloads only

## Event subscriber rules
- validate schema and version
- check idempotency store before processing
- use bounded retries
- move unrecoverable events to dead letter queue

## Inputs
- domain changes from crawl, feature, pattern, recommendation, execution, and outcome systems

## Outputs
- validated event envelopes dispatched to subscribers

## Data models
- ProcessedEvent with event_id, handler_name, processed_at
- DeadLetterEvent with event_id, reason, attempts, payload

## Failure modes
- schema mismatch
- broker unavailability
- subscriber lag

## Scaling considerations
- shard by event_type and campaign hash
- isolate high volume topics
- support consumer group scaling

## Example code snippet
    def publish(event_type, payload):
        envelope = build_envelope(event_type, payload)
        validate_envelope(envelope)
        broker_publish(event_type, envelope)

## Integration points
- execution lifecycle events
- policy update events
- observability event tracing

