# Org -> BusinessLocation Phase 2 Auto-Portfolio Spec

## Relationship Model

- Each `business_locations` record owns exactly one internal `portfolios` record by creation contract.
- `portfolios` remains the execution boundary and remains organization-scoped.
- `portfolios.business_location_id` is introduced as a nullable foreign key during this structural phase.
- `portfolios.business_location_id` references `business_locations.id` with `ON DELETE SET NULL`.
- `business_locations` does not gain a reverse foreign key or hard dependency on `portfolios`.
- Nullability is temporary for structural rollout safety and to avoid backfill in this phase.

## Invariants

- `portfolios.organization_id` must equal the owning `business_locations.organization_id` whenever `business_location_id` is set.
- No cross-organization linking is permitted.
- Replay hashing, replay inputs, and replay outputs remain unchanged.
- Fleet orchestration semantics and execution boundaries remain unchanged.
- Auth boundaries and RBAC behavior remain unchanged.
- Existing execution-layer `locations` remains untouched.

## Behavior Contract

- Future application logic will auto-create one internal `portfolios` row when a `business_locations` row is created.
- That portfolio is infrastructure-only and not a user-facing resource in standard UX.
- Standard users interact with `business_locations`, not directly with `portfolios`.
- The internal portfolio preserves current execution semantics while hiding portfolio as a UX concept.
- The model preserves future enterprise flexibility for more advanced mappings later.

## Rollout Notes

- This phase is structural-only.
- No auto-creation logic is introduced yet.
- No backfill is performed.
- Existing `portfolios` rows remain valid with `business_location_id = NULL`.
- Deterministic offline migration generation remains mandatory.

## Non-Goals

- No execution-layer `locations` changes.
- No reporting redesign.
- No multi-portfolio-per-business-location support in this phase.
- No backfill of existing portfolio rows.
- No UI exposure changes for portfolio in this phase.
- No replay, auth, or orchestration behavior changes.
