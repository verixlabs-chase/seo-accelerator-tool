# Portfolio Delegation and Recovery

## Purpose

ML1F adds the access and recovery controls required before InsightOS can offer
live multi-location Google Business Profile campaigns. It does not enable a
provider mutation. The only executable portfolio action remains the internal,
zero-credit `portfolio_review` readiness check.

## Delegated access boundary

Delegated access is always attached to one saved location group. A teammate
cannot receive portfolio-wide authority through this feature.

| Role | Read assigned group | Prepare frozen targets and runs | Pause, resume, retry | Approve a run |
| --- | --- | --- | --- | --- |
| Viewer | Yes | No | No | No |
| Operator | Yes | Yes | Yes | No |
| Approver | Yes | Yes | Yes | Yes |
| Organization owner/admin | All groups | Yes | Yes | Yes |

The access grant references both an active organization membership and a saved
location group in the same organization. Tenant-scoped foreign keys, API checks,
and PostgreSQL RLS keep the record inside that organization. Delegated users:

- see only assigned groups, target snapshots, and fleet runs;
- must create a target snapshot from an assigned group;
- cannot add or exclude a location outside that group;
- need operator authority to prepare or operate a run;
- need separate approver authority to start approved work; and
- lose access immediately when the grant is revoked.

Owners and administrators manage grants by teammate email. The teammate must
already be an active organization member. Invitation and teammate-management UI
remain part of COM1; the access-control API is ready for that UI.

## Pause and resume semantics

Pausing a portfolio run prevents undispatched location jobs from beginning. It
does not cancel an already-running provider or internal operation and never
deletes a completed result.

1. The service locks and refreshes the parent run.
2. A pause is accepted only while the run is active and at least one location is
   still waiting.
3. Queue selection excludes child jobs whose portfolio parent is paused.
4. A worker that receives an older queued message checks the parent and exits
   with `run_paused` before changing item state or calling a handler.
5. Resume refreshes every location from durable child-job state and dispatches
   only still-queued locations.
6. If all in-flight work finished while the run was paused, resume reports the
   honest terminal state instead of restarting completed work.

Pause and resume are version checked and audit logged with the frozen target
hash, actor, waiting count, and completed count.

## Shared Insight Credit guardrail

Preflight shows the organization's pooled remaining Insight Credits and the
estimated run total. Approval repeats that organization-level check while the
run is locked. A run fails closed with `fleet_credit_allowance_exhausted` when
the estimate no longer fits.

The current internal readiness action costs zero credits and creates no cost
ledger entry. G1.4B must add an idempotent provider-cost reservation before it
can dispatch any paid profile action. The existing cost ledger remains the
authority that prevents two concurrent campaigns from exceeding the shared
monthly allowance; a visual preflight estimate alone is never authorization to
spend.

## API surface

- `GET /organizations/{organization_id}/portfolio-access-grants`
- `POST /organizations/{organization_id}/portfolio-access-grants`
- `POST /organizations/{organization_id}/portfolio-access-grants/{grant_id}/revoke`
- `POST /organizations/{organization_id}/portfolio-fleet-runs/{run_id}/pause`
- `POST /organizations/{organization_id}/portfolio-fleet-runs/{run_id}/resume`

Existing location-group, target-snapshot, and portfolio-run reads are filtered
to assigned groups for delegated users. Existing create, approval, and recovery
routes enforce the role matrix above.

## Release boundary

Before live fleet mutations are enabled, G1.4B still needs typed campaign
content, Google authorization and quota preflight, per-location previews,
provider receipts, paid credit reservation/reconciliation/release, and a
production-owned-profile validation. No generic profile-edit batch is allowed.
