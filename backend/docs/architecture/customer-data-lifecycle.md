# Customer Data Lifecycle and Portability

Status: GOV1A account export and GOV1B Google disconnect are implemented locally
on 2026-08-13. Account closure, verified deletion, legal hold, and backup-erasure
workflows remain future GOV1 slices and must not be represented as complete.

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
| Identity and membership | User email, role, organization membership | Personal | Active account lifecycle; member facts are included in owner exports | User deletion, closure, hold, and backup rules |
| Authentication | Password hashes, sessions, refresh state | Restricted | Never exported; retained only for active security/session operations | Verified account deletion and session revocation proof |
| Connected-account secrets | OAuth tokens, provider credentials, webhook secrets | Restricted | Never exported. Google disconnect attempts outside revocation, always deletes the local grant, clears connection secrets, and records the result | Extend the same contract to later providers; add credential rotation controls |
| Business setup | Locations, campaigns, services, service areas | Customer confidential | Included in owner exports | Closure/deletion propagation |
| Search and business measurements | Rankings, history, connection mappings/status | Customer confidential | Supported facts included; secret connection metadata excluded | Full measurement inventory and deletion propagation |
| Recommendations and work | Governed recommendations, saved decisions | Customer confidential | Included in owner exports | Execution-record coverage and deletion propagation |
| Reports | Report metadata and artifact metadata | Customer confidential | Metadata included; binary artifacts excluded from GOV1A JSON | Governed artifact bundle export and retention rules |
| Imports | Import batches, source record states, review outcomes | Customer confidential | Supported records and provenance included | Upload parts expire after seven days; closure propagation remains |
| Account exports | Portable JSON artifact, hash, status, audit timestamps | Customer confidential | Downloadable for seven days, then artifact content is removed; status/hash/audit remain | Customer-configurable policy only after legal/security review |
| Billing identifiers | Customer/subscription/provider IDs | Restricted commercial | Never exported in the customer-data artifact | Document separate finance retention and deletion rules |
| Security and audit evidence | Audit events, incidents, legal holds | Restricted | Never placed in the customer export | Approved immutable retention and hold-release process |
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

GOV1 does not yet delete a user, close an organization, erase a backup, release
a legal hold, or export report binaries. Those workflows must
not be enabled until their dependency ordering, hold behavior, recovery window,
backup tombstones, audit proof, and production restore tests are complete.

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
