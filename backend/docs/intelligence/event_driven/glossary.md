# Glossary

## System definition
Canonical dictionary for event driven intelligence terminology.

## Terms
- EventEnvelope: versioned event message wrapper with metadata and payload.
- Idempotency key: stable key used to block duplicate processing.
- Deterministic hash: stable digest of canonical event content.
- Transition state: current pipeline stage for a campaign.
- Feature dependency map: map of changed signals to affected features.
- Simulation job: queued Digital Twin evaluation request.
- Dead letter queue: storage for unrecoverable events.
- Replay: deterministic reprocessing from a checkpoint.
- Backpressure: controlled throttling during overload.
- Policy update: deterministic weight adjustment from outcomes.
- Cohort pattern promotion: promotion of validated cross campaign pattern to long term memory.

## Purpose
Ensure engineers and AI agents use consistent language and contracts.

## Inputs
- architecture and service contracts

## Outputs
- shared vocabulary for design and implementation

## Data models
- glossary entries are mapped to model and event contract references

## Failure modes
- ambiguous terms causing implementation drift

## Scaling considerations
- version glossary alongside event schema versions

## Example code snippet
    deterministic_hash = sha256(canonical_json(payload))

## Integration points
- all docs in docs event_driven_intelligence
- schema contracts and API documentation

