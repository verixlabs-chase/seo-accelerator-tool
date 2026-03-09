# Org -> BusinessLocation Phase 1 Spec

## Defined Terms

- Organization: The top-level customer or internal account boundary represented by `organizations.id`.
- BusinessLocation: A new canonical organization-scoped business entity representing a real-world business location record for hierarchy and identity purposes only.
- Execution Location: The existing `locations` table entity used by portfolio and fleet execution.
- Tenant Isolation: The invariant that all persisted entities remain scoped to a single owning organization and no cross-organization read or write path is introduced.
- Scope: Phase 1 is limited to additive schema introduction for a canonical hierarchy root below Organization.

## Goals

- Introduce an additive `business_locations` table owned by `organizations`.
- Preserve backward compatibility and zero behavior change.
- Preserve migration determinism in online and offline Alembic modes.
- Preserve replay safety and auth boundary behavior.

## Non-Goals

- No coupling to execution-layer `locations` in Phase 1.
- No ORM wiring.
- No RBAC changes.
- No API changes.
- No provider credential changes.
- No reporting changes.
- No backfill or seed data.

## Backward Compatibility Guarantee

- Existing tables, including `locations`, remain unmodified.
- Existing query paths, orchestration flows, and replay paths remain unchanged.
- The new table is additive-only and unused by runtime logic in Phase 1.

## Existing Locations Boundary

- The current `locations` table remains the execution-layer entity for fleet and portfolio orchestration.
- Phase 1 must not rename, alter, repurpose, or add foreign keys to `locations`.
- Any future mapping from `business_locations` to execution `locations` is deferred to a later additive phase.

## Migration Determinism Requirement

- The migration must be offline-safe on first introduction.
- The migration must use pure structural DDL only.
- The migration must not depend on runtime inspection, seed logic, or data backfills.
- `alembic upgrade head --sql` must remain fully green after the change.

## Replay Safety Requirement

- No replay-governed tables or replay input/output paths are modified.
- No new runtime writes are introduced.
- No replay hashes, idempotency keys, or governance semantics are changed.
- Replay determinism test coverage must remain green.

## Auth Boundary Invariants

- `business_locations` is organization-scoped through `organization_id`.
- No auth policy behavior changes occur in Phase 1.
- No new cross-organization access path is introduced.
- Auth regression tests must remain green.

## Rollback Safety

- Rollback is a single Alembic downgrade of the additive migration.
- Because no existing tables are modified and no data is backfilled, rollback only drops the new table and its index.
- Rollback leaves existing execution and governance domains unchanged.

## Future Mapping Plan

- A future additive phase may introduce `business_location_id` on execution-layer entities, potentially including `locations`.
- Any future mapping must be dual-write or phased and must preserve replay determinism and tenant isolation.
- Execution coupling is explicitly out of scope for Phase 1.
