# Distributed Event System

`app/events/event_stream.py` provides the durable event surface used by the canonical event bus. Redis Streams is the production backend. Test mode uses an in-memory adapter with the same API.

Current guarantees:

- persistent event IDs
- consumer checkpoints
- retries for failed deliveries
- dead-letter capture
- idempotent acknowledgement by event ID

This is durable enough for multi-worker processing, but it is still a thin abstraction and not yet a full replay/audit platform.
