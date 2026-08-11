# Governed portfolio targeting

## Purpose

Portfolio targeting separates two decisions that must not be conflated:

1. which locations normally belong together; and
2. which exact locations a future bulk action may affect this time.

Saved location groups solve the first problem. Immutable target snapshots solve
the second. This slice does not execute a provider or website mutation.

## Data model

- `portfolio_location_groups` stores a reusable, organization-scoped group and
  an optimistic-lock version.
- `portfolio_location_group_members` stores the current group membership. A
  composite foreign key prevents a group from referencing a business location
  owned by another organization.
- `portfolio_target_snapshots` stores the group version, explicit filters,
  exact ready targets, explained exceptions, action key, idempotency key, and a
  canonical SHA-256 fingerprint.

PostgreSQL grants the application role only `SELECT` and `INSERT` on target
snapshots. Separate RLS policies allow scoped reads and inserts, with no update
or delete policy. Once a list is frozen, later group edits cannot rewrite what
an administrator reviewed.

## API

- `GET /api/v1/organizations/{organization_id}/location-groups`
- `POST /api/v1/organizations/{organization_id}/location-groups`
- `PATCH /api/v1/organizations/{organization_id}/location-groups/{group_id}`
- `GET /api/v1/organizations/{organization_id}/target-snapshots`
- `POST /api/v1/organizations/{organization_id}/target-snapshots`

All routes require an organization owner or administrator in the same
organization. Location identifiers are resolved only inside that organization;
an unavailable or foreign identifier returns a generic scoped error rather than
revealing another account's data.

## Deterministic target resolution

The caller must explicitly choose a saved group, all active locations, or one
or more included locations. There is no implicit “all locations” default.

Resolution order is stable:

1. load the saved group or explicitly selected active base;
2. intersect the base with any region filter;
3. add explicit inclusions;
4. apply explicit exclusions last;
5. require an active business location and an assigned campaign;
6. sort targets and exceptions by stable customer-visible fields; and
7. hash the canonical action, selection, targets, and exceptions.

An idempotency key may replay only when the newly resolved fingerprint matches
the saved record. Reusing the key for a different list fails with a conflict.

## Execution boundary

The next ML1 slice may consume a saved target snapshot to create durable fleet
jobs, but it must not recompute or expand the target set during execution. It
must add preflight cost and capability checks, an explicit approval boundary,
per-location idempotency, bounded concurrency, partial-failure recovery, and
aggregate progress that preserves every location result.
