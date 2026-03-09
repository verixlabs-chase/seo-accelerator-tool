# Organization -> Location Hierarchy Specification

## 1. Executive Summary

This specification introduces a backward-compatible `Organization -> Location` hierarchy into the Local SEO Operating System (LSOS) without breaking existing tenant isolation, organization-level billing, feature gating, provider credential management, portfolio intelligence, fleet orchestration, or the reporting engine.

The change is additive, uses phased rollout with dual-read compatibility, and assumes:

- live production traffic
- non-trivial tenant data volume
- zero tolerance for cross-tenant leakage
- zero tolerance for breaking schema changes

The hierarchy formalizes the distinction between the billing and security tenant boundary (`organization`) and the execution/reporting unit (`location`). Existing organization-scoped systems remain authoritative. Location scope is introduced as an optional child dimension that can be enabled incrementally behind feature flags and rolled out by canary cohort.

## 2. Defined Terms (Strict Definitions)

`Organization`
: The top-level tenant boundary. It owns billing, plan enforcement, provider credentials, feature entitlements, portfolio state, and all subordinate locations.

`Location`
: A tenant-scoped operational unit belonging to exactly one organization. A location represents a physical or logical business presence that can own localized SEO assets, execution state, reports, and provider mappings. A location never crosses organization boundaries.

`Tenant Isolation`
: The invariant that data, credentials, execution, and reporting for one organization are inaccessible to all other organizations unless explicitly permitted by an audited system operator path.

`Organization Scope`
: A query, policy, or write path constrained only by `organization_id`.

`Location Scope`
: A query, policy, or write path constrained by both `organization_id` and `location_id`, where `location_id` must belong to the same `organization_id`.

`Dual-Read`
: A compatibility mode where read paths can resolve data from legacy organization-only records or new organization-plus-location records.

`Dual-Write`
: A compatibility mode where writes continue to preserve legacy organization-level state while optionally persisting location-level projections or relationships.

`Feature Flag`
: A deterministic rollout control that gates behavior by environment, organization, and optionally location cohort.

`Replay Determinism`
: The requirement that a historical input snapshot re-executed through the same engine version yields the same normalized outputs, ordering, hashes, and side effects.

`Schema Drift`
: Any difference between intended migration state and the actual live database schema, indexes, constraints, or defaults.

## 3. Current System Constraints

Current architecture constraints that must remain true:

- `organization_id` is the authoritative multi-tenant boundary.
- Billing is enforced at organization level and must not fragment to per-location billing authorities.
- Feature gating is organization-first and may only be refined by optional child-level eligibility.
- Provider credentials are organization-owned and must not be duplicated across locations unless explicitly required by provider-specific alias mappings.
- Portfolio intelligence remains organization-centric because executive allocation and strategy decisions aggregate across all managed units.
- Fleet orchestration must be able to target multiple execution units, but global scheduling, queue fairness, and throttle policy remain organization-aware.
- Reporting must continue to support organization-level rollups and must gain location-level breakdowns without changing historical organization totals.
- Existing APIs and automation consumers may assume organization-only payloads and must not be broken.

Non-negotiable compatibility rules:

- no destructive column renames
- no hard requirement for `location_id` on existing records in phase 1
- no immediate foreign key backfill that blocks writes
- no query path that trusts `location_id` without validating `organization_id`

## 4. Target Architecture

The target model keeps `organization` as the root tenant and introduces `location` as a subordinate domain entity.

```text
Organization (security + billing + entitlements + provider credentials + portfolio control plane)
  -> Location (execution unit + localized SEO assets + local reporting dimensions)
    -> Campaigns / Listings / Content Targets / Sync Jobs / Report Slices
```

Architectural principles:

- organization remains the source of truth for entitlement, billing, plan controls
- location becomes the unit for localized execution, segmentation, and reporting dimensions
- every location-scoped write path carries both `organization_id` and `location_id`
- every location-scoped read path validates membership using a canonical organization-location relationship
- cross-location aggregation flows upward into organization-scoped portfolio intelligence

Proposed service layering:

- `OrganizationService`: remains authoritative for tenant lifecycle, billing, plan controls
- `LocationRegistryService`: new authoritative membership layer for location lifecycle and status
- `LocationScopedQueryGuard`: shared guard that resolves and validates `(organization_id, location_id)` pairs
- `LocationProjectionAdapter`: compatibility adapter for modules that can optionally read location detail
- `PortfolioAggregationAdapter`: normalizes location outputs back into stable organization-level portfolio inputs

## 5. Database Schema Changes (Backward Compatible)

### 5.1 New Tables

Add a new `locations` table:

```sql
CREATE TABLE locations (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL,
    external_ref VARCHAR(128) NULL,
    slug VARCHAR(128) NOT NULL,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    timezone VARCHAR(64) NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMPTZ NULL,
    CONSTRAINT fk_locations_organization
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
);
```

Indexes:

```sql
CREATE UNIQUE INDEX uq_locations_org_slug
    ON locations (organization_id, slug)
    WHERE archived_at IS NULL;

CREATE INDEX ix_locations_org_status
    ON locations (organization_id, status);

CREATE INDEX ix_locations_external_ref
    ON locations (organization_id, external_ref)
    WHERE external_ref IS NOT NULL;
```

### 5.2 Additive Columns to Existing Tables

Add nullable `location_id` columns to location-eligible tables only. Phase 1 keeps them nullable.

Illustrative examples:

```sql
ALTER TABLE campaigns
    ADD COLUMN location_id BIGINT NULL;

ALTER TABLE reporting_runs
    ADD COLUMN location_id BIGINT NULL;

ALTER TABLE listing_sync_jobs
    ADD COLUMN location_id BIGINT NULL;
```

Add non-blocking foreign keys after backfill readiness:

```sql
ALTER TABLE campaigns
    ADD CONSTRAINT fk_campaigns_location
    FOREIGN KEY (location_id)
    REFERENCES locations(id)
    NOT VALID;

ALTER TABLE reporting_runs
    ADD CONSTRAINT fk_reporting_runs_location
    FOREIGN KEY (location_id)
    REFERENCES locations(id)
    NOT VALID;
```

Then validate asynchronously:

```sql
ALTER TABLE campaigns VALIDATE CONSTRAINT fk_campaigns_location;
ALTER TABLE reporting_runs VALIDATE CONSTRAINT fk_reporting_runs_location;
```

### 5.3 Integrity Guardrails

To prevent auth leakage, location-scoped rows must preserve organization congruence:

- application layer must validate `locations.organization_id = <request.organization_id>`
- for high-risk tables, introduce deferred composite guards via trigger or composite lookup table if the database cannot express cross-table dual-column FK safely without major rewrites

Optional trigger for critical write paths:

```sql
CREATE OR REPLACE FUNCTION enforce_location_belongs_to_org()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.location_id IS NULL THEN
        RETURN NEW;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM locations l
        WHERE l.id = NEW.location_id
          AND l.organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'location_id does not belong to organization_id';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

This trigger must be applied only after query plans and write amplification impact are measured in staging.

## 6. Migration Strategy (Zero Downtime + Idempotent)

### 6.1 Migration Ordering

Apply in strict order:

1. create `locations` table
2. create additive indexes on `locations`
3. add nullable `location_id` columns to selected tables
4. deploy application code with write-path awareness but feature-flagged off
5. enable dual-read paths for safe lookup and telemetry only
6. backfill seeded location records for canary organizations
7. start dual-write for approved modules
8. add `NOT VALID` foreign keys
9. validate constraints in controlled windows
10. enable organization-level canary cohort
11. expand rollout gradually
12. only after full confidence, consider selective `NOT NULL` promotion for net-new tables, never for legacy rows without a completed backfill plan

### 6.2 Idempotent Migration Rules

Every migration must be rerunnable or safely no-op:

- guard table creation with existence checks where framework supports it
- guard column additions with `IF NOT EXISTS`
- never embed irreversible data transforms in schema migrations
- write backfill scripts so they can resume by checkpoint and skip already processed rows

Example:

```sql
ALTER TABLE campaigns
    ADD COLUMN IF NOT EXISTS location_id BIGINT NULL;
```

### 6.3 Zero-Downtime Backfill

Backfill approach:

- create default location records only for organizations explicitly enabled for the feature
- chunk by organization and primary key window
- use bounded transactions
- record checkpoints in a dedicated migration journal table
- throttle to avoid lock and replication pressure

Default mapping policy:

- legacy organization-only records remain valid with `location_id IS NULL`
- where deterministic one-to-one mapping is known, backfill `location_id`
- where ambiguity exists, defer assignment until operationally resolved

### 6.4 Rollback Strategy

Rollback must be incremental and reversible:

1. disable write-path feature flags
2. disable read-path location expansion
3. stop backfill workers
4. preserve newly added schema objects
5. revert to organization-only reads
6. leave `location_id` columns nullable and unused

Do not drop columns, tables, or constraints during incident rollback unless a separate, approved emergency migration is prepared and tested.

## 7. RBAC Extension (No Breaking Changes)

RBAC must remain organization-rooted.

Additive permission model:

- existing organization roles remain valid with no changes
- new optional location-scoped grants narrow access within an organization but never widen it across organizations
- absence of location grant defaults to current organization-level semantics for legacy users, subject to feature flag state

Proposed authorization checks:

1. authenticate principal
2. resolve organization membership
3. if endpoint is location-scoped, verify location belongs to organization
4. evaluate role capability
5. if location restrictions exist for the principal, verify requested location is in scope

No-breaking-change rules:

- existing org admins continue to operate across all organization locations unless explicitly restricted by a new policy toggle
- existing service accounts remain organization-scoped by default
- new location manager roles are additive only

Example policy matrix:

| Role | Org Read | Org Write | Location Read | Location Write | Billing |
| --- | --- | --- | --- | --- | --- |
| Org Admin | Yes | Yes | All | All | Yes |
| Org Analyst | Yes | No | All | No | No |
| Location Manager | No | No | Assigned | Assigned | No |
| Service Account | Configured | Configured | Configured | Configured | No |

Mandatory regression safeguard:

- every auth path must verify `organization_id` first, then apply optional `location_id` narrowing

## 8. Module Impact Analysis (Per Engine)

### 8.1 Billing Engine

- no billing ownership change
- organization remains invoice owner
- location counts may inform plan limits, quota enforcement, and overage reporting
- billing calculations must not multiply charges unless a pricing rule explicitly references active location count

### 8.2 Feature Gating Engine

- retain organization-level feature evaluation as the root decision
- introduce optional child flag `org_location_hierarchy.enabled`
- support additional sub-flags for module rollout:
  - `org_location_hierarchy.api_reads`
  - `org_location_hierarchy.reporting`
  - `org_location_hierarchy.fleet_execution`
- all new code paths must fail closed when flags are disabled

### 8.3 Provider Credential Model

- provider credentials remain organization-owned
- add optional `location_provider_binding` projection only when a provider requires mapping a location to an organization-owned credential alias or remote listing identifier
- never duplicate raw credential secrets per location

### 8.4 Portfolio Intelligence Foundation

- keep organization as the primary portfolio boundary
- aggregate location signals into normalized organization-level inputs
- preserve deterministic ranking by incorporating `location_id` only as a stable secondary dimension in location-aware engines
- replay snapshots must include both organization aggregate and location lineage metadata when location mode is enabled

### 8.5 Fleet Orchestration

- scheduler remains organization-aware for queue fairness and rate limits
- execution targets may fan out per location
- circuit breakers must support disabling a single location without suspending the entire organization unless risk policy escalates

### 8.6 Reporting Engine

- preserve current organization reports unchanged
- add optional location dimension filters and breakdowns
- materialized reporting views must remain backward-compatible with existing consumers
- report cache keys must include `location_id` only when a location filter is present

### 8.7 API Layer

- all existing organization-level endpoints remain stable
- add optional `location_id` filters or nested location endpoints
- no mandatory request contract changes in phase 1

### 8.8 Background Jobs and Replay

- job payloads must carry `organization_id`
- when location-scoped, job payloads must also carry `location_id`
- deduplication keys and replay hashes must include `location_id` only when relevant to preserve deterministic identity

## 9. Regression Protection Strategy (Explicit)

Explicit safeguards required before each rollout increment:

- preserve legacy organization-only code path as the default until the cohort is promoted
- gate all new behavior behind explicit feature flags
- deploy read support before write support
- deploy write support before any strict constraints
- maintain compatibility serializers that omit `location_id` when the caller is on a legacy contract

Regression suites must explicitly verify:

- no change to organization-scoped totals when `location_id` is unused
- no cross-organization reads using forged `location_id`
- no provider credential leakage across locations or organizations
- no billing ownership drift from organization to location
- no change in portfolio ranking determinism for unaffected tenants
- no queue starvation after fan-out by location
- no report cache contamination between org-level and location-level queries

Operational kill switches:

- disable all location reads
- disable all location writes
- disable location backfill workers
- disable location-scoped execution fan-out

## 10. API Contract Adjustments

Phase 1 contract posture is additive only.

### 10.1 Existing Endpoints

Support optional query parameters:

```http
GET /api/v1/reports?organization_id=42&location_id=1001
GET /api/v1/campaigns?organization_id=42&location_id=1001
```

Rules:

- `location_id` is optional
- if provided, server validates that the location belongs to the authenticated organization
- if omitted, behavior remains unchanged

### 10.2 New Endpoints

Optional nested resources:

```http
GET /api/v1/organizations/{organization_id}/locations
POST /api/v1/organizations/{organization_id}/locations
GET /api/v1/organizations/{organization_id}/locations/{location_id}
PATCH /api/v1/organizations/{organization_id}/locations/{location_id}
```

### 10.3 Response Compatibility

Existing payloads may add nullable fields:

```json
{
  "organization_id": 42,
  "location_id": 1001,
  "location_name": "Austin North",
  "campaign_id": 7781
}
```

Compatibility rules:

- new fields must be additive and nullable
- existing field semantics must remain unchanged
- webhooks must version-gate any new location fields to avoid downstream parser breakage

## 11. Phased Rollout Plan

### Phase 0: Design and Guardrails

- land schema migrations only
- keep all flags disabled
- ship observability and logging for membership validation

### Phase 1: Read-Only Canary

- enable `org_location_hierarchy.enabled` for internal test organizations only
- create locations and expose read-only APIs
- no execution writes yet

### Phase 2: Dual-Write Canary

- enable location writes for a small canary cohort
- persist optional `location_id` on selected modules
- compare legacy and location-aware outputs in shadow mode

### Phase 3: Controlled Expansion

- increase cohort by organization tier
- enable reporting and fleet fan-out in separate flags
- monitor query latency, auth denials, replay hash stability, and queue pressure

### Phase 4: General Availability

- keep backward-compatible organization-only contracts
- maintain kill switches
- postpone strict constraints until empirical stability is established

### Canary Deployment Instructions

For each canary wave:

1. select low-risk internal or pilot organizations
2. enable read flags only
3. run smoke, auth, replay, and report parity checks
4. enable write flags for one module at a time
5. observe for one full reporting cycle
6. expand only if all validation gates pass
7. immediately revert flags on any auth, schema, replay, or billing anomaly

## 12. Testing Requirements

Minimum mandatory validation for every implementation increment:

### 12.1 Unit Tests

- organization-location membership validation
- feature flag fallthrough
- RBAC narrowing behavior
- serializer backward compatibility
- deterministic hash generation with and without `location_id`

### 12.2 Integration Tests

- create organization, create location, execute scoped reads/writes
- enforce provider credential ownership at organization boundary
- verify reporting queries return correct organization rollups and location slices
- verify fleet jobs fan out only to authorized locations

### 12.3 Regression Suite

- full legacy organization-only workflow with no `location_id`
- replay historical event corpus and verify identical outputs for non-enabled tenants
- compare billing calculations before and after feature enablement
- validate auth rejection for mismatched `(organization_id, location_id)` pairs

### 12.4 Migration Validation

- run migrations in dry-run mode against production-like data volume
- verify lock profile, execution time, and rollback posture
- verify no schema drift after migration

### 12.5 Security and Auth Boundary Tests

- attempt horizontal access using valid `location_id` from another organization
- attempt stale role tokens with narrowed location access
- verify service accounts cannot exceed configured location scope

### 12.6 CI Validation Checklist

- run unit tests
- run integration tests
- run regression suite
- run migration dry-run
- verify schema drift detection passes
- verify replay determinism check passes
- verify auth boundary regression checks pass
- verify contract snapshots for legacy API consumers remain unchanged unless explicitly versioned

## 13. Future Extension Hooks

The design should preserve clean extension points without forcing near-term adoption:

- optional location groups for regional rollups
- optional per-location SLA policy overlays, still subordinate to organization plan constraints
- optional provider alias bindings for location-specific remote entities
- optional location-level budget segmentation for analytics only, not billing authority
- optional location archive and transfer workflows within the same organization

Future changes must continue to preserve:

- organization as the tenant root
- billing at organization scope
- provider secrets at organization scope
- deterministic replay identity
- additive-only API evolution

## Save and Validation Procedure

Save this document at:

`docs/architecture/org_location_hierarchy_spec.md`

Before any implementation proceeds, run all of the following:

1. save the file and verify it is tracked by Git
2. run the full unit test suite
3. run the full integration test suite
4. run the regression suite
5. run migration dry-run mode against production-like data
6. confirm no schema drift
7. confirm replay determinism integrity
8. validate RBAC behavior
9. confirm no auth boundary leakage
10. pause for review before any code or migration rollout
