# Approval-gated portfolio fleet runs

## Purpose

ML1E turns an immutable `PortfolioTargetSnapshot` into reviewable work without
weakening InsightOS's location isolation. A `PortfolioFleetRun` is the
organization-level parent. Each ready location receives one existing
portfolio-scoped `FleetJob`, so concurrency, item locking, idempotency, circuit
breakers, and failed-item retry continue to live in the established Fleet
worker layer.

This slice supports only `portfolio_review`, an internal readiness check. The
handler rejects any `provider_call` and the customer contract always reports
`provider_changes_enabled: false`. Google Business Profile posts, photos, and
profile edits remain disabled until the typed G1.4B capability, policy, quota,
and production-access gates are complete.

## Customer flow

1. An owner or administrator freezes the exact locations in a target snapshot.
2. `POST /organizations/{org}/portfolio-fleet-runs` rechecks every frozen
   location and stores a preflight. It shows targeted, ready, blocked, and
   estimated Insight Credit counts. It does not create a worker job.
3. The customer reviews the location list and explicitly approves the run.
4. Approval creates one durable, idempotent Fleet job per ready location in the
   same transaction as the approval record. Dispatch happens only after commit.
5. Progress is reconciled from the child jobs without merging location truth.
6. If some locations fail, only failed locations can be requeued. Completed
   locations are not repeated.

Growth and Enterprise plans can create and approve these runs. A later
downgrade does not erase historical progress, but it blocks new bulk work.

## Stored truth

`portfolio_fleet_runs` stores:

- the immutable target snapshot id and hash;
- action key and idempotent request key;
- customer-visible preflight and Insight Credit estimate;
- request and approval actors and timestamps;
- aggregate ready, blocked, queued, running, succeeded, and failed counts;
- a manual version used to reject stale approvals and retries.

`portfolio_fleet_run_items` stores one location result with its campaign,
isolated portfolio, child Fleet job, capability decision, safe failure message,
and retry count. A unique run/location constraint prevents duplicate fan-out.

The preflight copies the frozen hash rather than rebuilding the target list. At
approval, current location, campaign, and portfolio availability are rechecked.
A location that became unavailable is blocked by itself and cannot expand or
replace the approved target set.

## State model

Parent states are `awaiting_approval`, `blocked`, `running`, `succeeded`,
`partial`, `failed`, and `cancelled`. `partial` is required whenever some work
succeeds while another selected location is blocked or failed. It is never
displayed as complete.

Location states are `ready`, `blocked`, `queued`, `running`, `succeeded`, and
`failed`. Customer responses translate these to plain language such as “Ready
for approval,” “Waiting,” “Complete,” and “Needs attention.” Raw provider error
bodies are not returned.

## Transaction and recovery guarantees

- Preflight creation is idempotent by organization and request key.
- Approval checks the customer's expected version and locks the parent row.
- Child Fleet jobs are prepared without dispatch, then approval, audit rows,
  run items, and jobs commit together.
- Queue submission is best effort after commit. Durable queued rows remain the
  recovery source during a broker interruption.
- Each child job uses `portfolio_review` plus a run/location idempotency key.
- Fleet processing keeps the existing per-portfolio concurrency cap and row
  locks.
- Retry selects only failed child jobs. It increments both Fleet and
  portfolio-run retry history and leaves successful locations unchanged.

## Cost and approval boundary

The current internal readiness action costs zero Insight Credits, but it uses
the same customer credit summary and persists a confirmed estimate before
approval. Future typed actions must add a deterministic credit estimate,
reserve credits before provider dispatch, reconcile or release the reservation,
and fail closed if the pooled allowance is unavailable.

An approved run is not evidence that rankings, visits, calls, or customer
actions improved. It proves only that the defined location work completed. Any
future external action must attach its own measurement contract and provider
receipt.

## Security

- All public routes require `org_owner` or `org_admin` and enforce organization
  context.
- Parent and item tables carry both tenant and organization ids and use
  PostgreSQL row-level security for the application role.
- Cross-organization snapshots return not found, and cross-organization route
  access returns forbidden.
- Target snapshots remain immutable to the application role.
- Audit events record preflight creation, approval, target hash, credit
  estimate, and failed-location retry.
