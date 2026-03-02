# Org -> BusinessLocation Phase 4 Execution Link Spec

## Purpose

Introduce an additive, optional structural relationship between execution-layer
`locations` and canonical `business_locations`.

This phase is structural-only. No behavior change.

## Relationship Model

- Add nullable column:
  - locations.business_location_id
- Foreign key:
  - fk_locations_business_location_id
  - references business_locations.id
  - ON DELETE SET NULL
- Add index:
  - ix_locations_business_location_id

## Invariants

- Cross-organization linkage is forbidden at the application layer.
- In this phase, the database does NOT enforce organization alignment.
- The only database-level guarantee introduced here is referential integrity
  on business_location_id -> business_locations.id.
- Organization alignment hard enforcement (e.g., composite FK, trigger, or
  check constraint) is explicitly deferred to a future phase.
- Replay hashing, replay inputs/outputs remain unchanged.
- Fleet orchestration semantics remain unchanged.
- Portfolio semantics remain unchanged.

## Non-Goals

- No backfill of existing rows.
- No non-null enforcement.
- No execution-layer renames.
- No ORM rewiring.
- No auto-assignment logic.
- No reporting changes.
- No UI changes.

## Determinism Requirement

- Migration must be offline-safe from day one.
- No inspection-based conditional DDL.
- alembic upgrade head --sql must remain fully deterministic.

## Enforcement Roadmap

- Phase 4A: Structural link only (nullable FK, index).
- Phase 4B: Service-layer enforcement of organization alignment.
- Phase 4C (optional future hardening):
  - Composite foreign key or trigger-based enforcement.
  - Potential non-null constraint after backfill.

## Rollback Safety

- Downgrade drops:
  - index
  - foreign key
  - column
- No data mutation required.
- Existing execution semantics remain intact.
