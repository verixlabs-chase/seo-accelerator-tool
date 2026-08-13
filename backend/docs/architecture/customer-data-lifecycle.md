# Customer Data Lifecycle and Portability

Status: GOV1A account export, GOV1B Google disconnect, and the GOV1C recoverable
workspace-closure slice are implemented locally on 2026-08-13. Verified
primary-store deletion, user deletion, artifact/cache inventory closeout, and
backup erasure verification remain future GOV1 slices and must not be
represented as complete.

## Principles

- Customer-facing exports contain customer business data, saved work, and
  supported measurements; they never contain authentication or provider
  credentials.
- Every export is tenant- and organization-scoped, restricted to an
  organization owner, integrity-checked, auditable, and time limited.
- Deletion must cover primary storage, queues, generated artifacts, caches, and
  backups without erasing evidence subject to a valid security or legal hold.
- Restores must reapply lifecycle tombstones so expired or deleted customer
  data is not silently resurrected.

## Data-class inventory

| Data class | Examples | Sensitivity | Current lifecycle | GOV1 completion work |
|---|---|---|---|---|
| Identity and membership | User email, role, organization membership | Personal | Member facts are included in owner exports; workspace closure does not delete a user who may belong to another organization | User deletion and verified membership erasure |
| Authentication | Password hashes, sessions, refresh state | Restricted | Never exported; organization sessions are revoked when the recovery window finishes | Verified user-account deletion proof |
| Connected-account secrets | OAuth tokens, provider credentials, webhook secrets | Restricted | Never exported. Google disconnect attempts outside revocation, always deletes the local grant, clears connection secrets, and records the result | Extend the same contract to later providers; add credential rotation controls |
| Business setup | Locations, campaigns, services, service areas | Customer confidential | Included in owner exports | Closure/deletion propagation |
| Search and business measurements | Rankings, history, connection mappings/status | Customer confidential | Supported facts included; secret connection metadata excluded | Full measurement inventory and deletion propagation |
| Recommendations and work | Governed recommendations, saved decisions | Customer confidential | Included in owner exports | Execution-record coverage and deletion propagation |
| Reports | Report metadata and artifact metadata | Customer confidential | Metadata included; binary artifacts excluded from GOV1A JSON | Governed artifact bundle export and retention rules |
| Imports | Import batches, source record states, review outcomes | Customer confidential | Supported records and provenance included | Upload parts expire after seven days; closure propagation remains |
| Account exports | Portable JSON artifact, hash, status, audit timestamps | Customer confidential | Downloadable for seven days, then artifact content is removed; status/hash/audit remain | Customer-configurable policy only after legal/security review |
| Billing identifiers | Customer/subscription/provider IDs | Restricted commercial | Never exported in the customer-data artifact | Document separate finance retention and deletion rules |
| Security and audit evidence | Audit events, incidents, legal holds | Restricted | Never placed in the customer export; only a platform owner can place or release a hold | Approved immutable retention periods and production operating procedure |
| Product analytics | Privacy-minimized product events | Internal/customer contextual | Governed by the PA1 event contract; no session replay | Publish retention and deletion behavior |

## GOV1A export contract

An organization owner calls the organization-scoped export endpoint with a
client request ID. The service creates one idempotent JSON artifact containing:

- organization-safe fields and member roles/emails;
- locations, campaigns, services, and service areas;
- connection mapping and health facts without tokens, cursors, or secret
  metadata;
- keyword groups, tracked searches, rankings, and ranking history;
- recommendations;
- report records, artifact metadata, and recipients without binary contents;
- migration batches and imported-record provenance;
- provider disconnect status and outside-revocation history without credentials.

The artifact explicitly records excluded sensitive classes. It is serialized
deterministically, hashed with SHA-256, size checked, stored with a seven-day
expiry, and served only through an authenticated owner-only endpoint with
private/no-store response headers. Download verifies the stored hash before
delivery and writes an audit event. A nightly task removes expired artifact
content while preserving the status, hash, timestamps, and audit trail.

## Explicit non-claims

GOV1C can close a workspace and make it ready for verified deletion, but it
does not yet claim that primary business rows, generated files, caches, or
backups are erased. It does not delete a user, because one user may belong to
more than one organization. The tombstone remains in
`pending_primary_erasure` until dependency-ordered erasure, artifact/cache
inventory checks, backup propagation, and restore verification are complete.
Report binary export also remains future work.

## GOV1B Google disconnect contract

Only an organization owner can disconnect Google. The owner first receives a
preview of affected locations, stopped updates, preserved record counts, and
the exact confirmation phrase. The operation is idempotent and applies to the
organization's shared Google grant, so Search Console, Business Profile,
Analytics, and private inquiry collection tied to that Analytics connection
cannot be presented as independent access switches.

On confirmation, InsightOS:

- attempts to revoke the refresh or access token through Google's revocation
  endpoint without logging or persisting the raw token;
- deletes the encrypted organization Google grant even when Google cannot
  confirm the outside revocation;
- marks every organization Google mapping disconnected, clears provider cursor
  and connection-secret metadata, and prevents new scheduled collection;
- cancels queued Google sync work and prevents late running work from changing
  the connection back from disconnected;
- preserves previously collected measurements, profile snapshots, search
  terms, owned reviews, analytics facts, reports, and recommendations;
- writes a durable owner/action/result record and a credential-free audit event.

If Google's endpoint is unavailable, the customer sees that InsightOS access
was removed but outside revocation was not confirmed, with a plain instruction
to review third-party access in their Google Account. Reconnecting creates a
new grant; removed private inquiry keys must be created again.

## GOV1C recoverable workspace-closure contract

Only an organization owner may schedule workspace closure, and an active paid
subscription must be ended first so closing the software cannot silently leave
provider billing active. The preview shows affected connections, schedules,
share links, queued jobs, the 30-day recovery window, and the exact confirmation
phrase.

Scheduling closure immediately:

- marks the organization `closure_pending` and centrally blocks customer write
  requests while leaving read access and owner export/recovery controls;
- pauses data mappings and WordPress access without deleting their encrypted
  credentials during the recovery window;
- disables report schedules, revokes public report links, and cancels queued
  platform jobs;
- saves a credential-free operational snapshot so safe mappings and schedules
  can be restored if the owner reopens the workspace;
- does not recreate revoked public links or canceled jobs after recovery;
- writes a durable owner/action/result audit record.

An owner may reopen the workspace before the recovery deadline. After the
deadline, a nightly finalizer first checks for an active retention/legal hold.
Only a platform owner can place or release that hold, its restricted reason is
never returned to the customer, and a normal owner request cannot bypass it.

When no hold exists, finalization deletes organization provider credentials and
organization OAuth client secrets, disconnects mappings, clears WordPress
secrets, disables schedules, revokes share links and organization sessions,
marks the workspace closed, and creates a restore-safe deletion tombstone. The
tombstone explicitly records that primary-store erasure is still pending and
must be reapplied after any backup restore.

## Release evidence

- Alembic migration creates the tenant-scoped export-request ledger and
  PostgreSQL row-level security policy.
- API tests prove owner-only creation/download, organization isolation,
  credential-safe contents, idempotency, integrity metadata, expiration, and
  durable audit events.
- Task tests prove the nightly artifact-retention job is registered.
- The Settings page explains what is included, what is excluded, who may
  download it, and when it expires without claiming deletion is complete.
- Provider disconnect tests prove owner-only scope, exact confirmation,
  credential deletion, outside-revocation truth, saved-result preservation,
  queued-job cancellation, audit safety, idempotency, and late-worker guards.
- Closure tests prove exact owner confirmation, organization isolation, active-
  billing blocking, central read-only enforcement, reversible safe state,
  non-restoration of revoked links/jobs, platform-owner-only holds, hold-aware
  finalization, credential/session removal, honest primary-data status, and
  restore-safe tombstone creation.
- The nightly closure finalizer is registered after the recovery window, and
  Alembic creates RLS-protected closure, hold, and tombstone ledgers that do not
  depend on the organization row surviving future primary-store deletion.
