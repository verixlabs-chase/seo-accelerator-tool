# Production Readiness Roadmap

Date: 2026-07-28

This is the authoritative gate roadmap for the Supabase and Vercel deployment.
Its phases are named **PR0-PR6** and do not replace or renumber customer product
sprints. Active Customer UX and Growth execution is defined in
[claude-next-build-brief.md](./claude-next-build-brief.md). Older audit documents
remain useful historical context, but their feature inventories are not the
current source of truth.

## Deployment target

- Windows-managed development and operations
- Supabase PostgreSQL
- Vercel FastAPI backend
- Vercel Next.js frontend
- no Docker, WSL, Bash, local PostgreSQL, or local Redis

## Current capability matrix

The live commercial-claim source of truth is now the append-only matrix at
`/platform/capabilities`. It is generated from the canonical commercial catalog
and current production receipts. Plan inclusion never means production-proven;
limited, unavailable, expired, and missing-proof states remain explicit. The
table below is an architectural roadmap snapshot and must not be copied into
pricing, demos, Help, or sales language without checking the live matrix first.
The corresponding whole-product route and moderated-usability evidence lives at
`/platform/experience`; automated suite results are not a substitute for its
desktop, mobile, and five-participant launch receipts.

| Capability | Current production state | Next gate |
| --- | --- | --- |
| Authentication | Working with HttpOnly access and refresh cookies | invitations, password recovery, session revocation, organization switcher |
| Tenant authorization | Enforced in API dependencies and service queries | explicit PostgreSQL RLS and least-privileged runtime database role |
| Database migrations | Windows GitHub Actions workflow applies Alembic migrations to Supabase | add a disposable PostgreSQL validation environment before production migration |
| Product frontend | The customer workspace, organized navigation, shared visual system, and primary product routes are implemented; a read-only browser launch journey passed against production on 2026-08-21 for authenticated Overview, Reports, location context, and desktop/mobile navigation | configure the protected GitHub smoke account, capture the automated workflow receipt, then complete the full OPS1F route matrix and moderated usability sessions |
| Multi-location hierarchy | Account groups, physical locations, hidden execution scopes, location campaigns, nested hierarchy API, and customer workspace are implemented | location KPI rollups, delegated location access, bulk actions, and legacy-record assignment |
| Interactive report generation | Works, but generated artifacts are local and non-durable on Vercel | upload artifacts to durable object storage |
| Scheduled report generation | First durable database-backed job type implemented | deploy migration `20260310_0071`, set `CRON_SECRET`, then expand queue coverage |
| Email delivery | Adapter contract exists; hosted configuration is optional | configure a real SMTP provider and verify delivery outcomes |
| Crawling | Small request-based crawls can execute eagerly | convert crawl frontier steps to durable jobs before increasing limits |
| Rankings | Real SerpAPI adapter exists | select backend, configure organization credentials, and validate a live campaign |
| Local visibility / reviews | Base location map and G1.2 queued, credit-controlled local rank grid are live. G1.4's authorized listing mapping, snapshots, field checks, performance history, customer search terms, and customer UI are implemented locally. G1.6A owned-review truth, G1.6B governed credit-controlled drafts, G1.6C explicitly confirmed direct-reply execution, G1.6D1 evidence-backed location and portfolio review intelligence, G1.6D2A governed passive requests, and browser-local downloadable QR generation are implemented locally. Request campaigns enforce one audience rule for all eligible customers, durable consent and suppression, and non-causal result reporting. Automatic replies remain off; direct posting and request delivery fail closed until their respective live capabilities are proven. | obtain Google Business Profile API project approval; prove one live sync, governed draft, customer-confirmed reply, exact provider receipt, and access-revocation path; validate G1.6D1 across production locations; then connect G1.6D2B transactional email, price-card credits, and signed outcome webhooks. SMS stays gated behind a separate provider and compliance launch decision |
| Citations / backlinks | Synthetic provider is test-only | implement G1.5 listings/citations provider first, then CNT1 editorial authority data |
| Competitors | Stored-dataset workflow works | add durable collection and a live upstream provider if required |
| Recommendations | Heuristic generation and governance are implemented | validate recommendations against live provider inputs |
| Executions | Approval, dry-run, retry, cancel, rollback, and audit UI exist | validate a real WordPress integration before enabling live mutations |
| Generic background tasks | Celery runs eagerly in hosted mode | move job types incrementally onto `platform_jobs` |
| Rate limiting | Disabled in hosted mode because Redis is absent | implement a database or managed edge-compatible limiter |
| Usage economics | Provider calls and entitlement consumption are counted, but currency cost and margin are not reconciled | add platform-vs-organization credential attribution, cost reservations, reconciliation, and hard monthly spend stops |
| Commerce | Tier and entitlement foundations exist, but customer billing is not implemented | implement COM1 checkout, subscription lifecycle, enforced allowances, account recovery, and plan-change workflows |
| External automation | Signed, encrypted, outbound-only delivery for Zapier, Make, Pipedream, and published n8n Cloud workflows is implemented locally with durable retry, dead-letter recovery, a versioned starter recipe catalog, provider-specific wiring kits, deterministic receiver conformance fixtures, monthly delivery visibility, official documentation handoffs, and receipt-backed connection proof; no connected tool can run an InsightOS action | capture live provider-by-provider production proof and publish reviewed external-platform templates, then add scoped credentials, replay-protected typed commands, action allowances, and audit proof before enabling inbound automation or generic/customer-hosted endpoints |
| Frontend testing | 311 deterministic frontend contract tests, a local Playwright public sign-in pass, and a non-mutating authenticated production browser pass with zero captured console warnings or errors; a protected manual GitHub workflow is fixed to the production hostname | configure `E2E_SMOKE_EMAIL` and `E2E_SMOKE_PASSWORD`, capture the first automated run, then expand evidence across every OPS1F route and viewport |
| Backend testing | Large SQLite suite and migration validation | PostgreSQL API, concurrency, lease, and RLS integration lanes |

## Durable-job architecture

Migration `20260310_0071` turns the existing `platform_jobs` table into the
Supabase-backed queue:

- globally unique idempotency keys
- scheduled availability
- worker ownership
- expiring leases
- stale-lease recovery
- bounded exponential retry
- dead-letter state
- `FOR UPDATE SKIP LOCKED` claims on PostgreSQL

Vercel Cron calls:

```text
GET /api/v1/internal/jobs/drain
Authorization: Bearer <CRON_SECRET>
```

The first registered handler is `reporting.process_schedule`. A due report
schedule is converted to one idempotent job, leased, executed, and advanced to
its next run. More handlers should be migrated one at a time with tests.

The committed cron expression is daily at 06:00 UTC so it is valid on Vercel
Hobby as well as paid plans. Paid plans can increase the frequency after
monitoring execution duration and database load.

## Multi-location architecture

Migration `20260728_0072` formalizes the customer-facing hierarchy:

```text
Organization
  -> SubAccount (client, brand, region, or division)
    -> BusinessLocation (physical location)
      -> Campaign
```

Each business location automatically owns one hidden internal portfolio and,
when assigned to a subaccount, one execution location. Campaigns inherit the
business location's subaccount and internal portfolio. The `/locations`
workspace exposes only the customer concepts and reports legacy unassigned or
inconsistent records instead of silently blending them into rollups.

## Next product integration boundary

The next data product phase is **Growth G1 - Automated Data Connections**. Its
purpose is to remove recurring manual data entry for approved search and website
signals while preserving source truth, tenant isolation, and per-location scope.

Included in G1:

- Google Search Console
- DataForSEO-backed local rank grids with explicit customer confirmation and
  allowance checks
- Google Business Profile
- approved review monitoring, response, and generation providers
- approved listing/citation discovery, correction, and submission providers
- website analytics and website form-conversion events
- organization-owner connection and reconnection flows
- external property/profile mapping to the correct subaccount, business
  location, website, and campaign
- initial backfill, durable scheduled synchronization, retry safety,
  deduplication, freshness, audit history, and user-visible connection health
- provider cost estimation, reservation, reconciliation, and hard allowance
  enforcement before platform-paid work

Excluded from G1:

- call-tracking providers and call ingestion
- CRM connections
- field-service and job-management systems
- booked-job, estimate, pipeline, payment, and revenue imports
- sales or revenue attribution

These exclusions apply to schema, API, job, provider-adapter, and UI work. A
later phase must receive explicit scope approval before any excluded connection
is designed or implemented.

## Implementation phases

### PR0: production truth and repository hygiene

- maintain this capability matrix
- archive or label obsolete audit documents
- remove tracked logs, backups, and temporary test output
- keep deployment instructions synchronized with production behavior

### PR1: durable execution

1. Scheduled reports
2. Crawl frontier batches
3. Ranking collection
4. Local/review collection
   - require estimate, reservation, reconciliation, and organization spend-limit checks before enabling customer-run geo-grid tasks
   - fan G1.4B profile campaigns into bounded, idempotent per-location jobs;
     preserve the approved target snapshot, respect Google quotas, and expose
     partial failure, pause, resume, safe retry, and provider receipts
5. Citation and authority refresh
6. Growth G1 search, profile, website analytics, and form-event synchronization
7. Intelligence and automation cycles
8. AUT1 outbound webhook deliveries and accepted inbound commands

Each migration requires:

- an idempotency key
- a bounded unit of work
- retry classification
- a terminal dead-letter state
- a status visible to the user
- an integration test proving duplicate invocation safety

### PR2: database and identity security

- use a least-privileged application database role instead of an owner role
- set tenant context transactionally
- add explicit RLS policies for tenant-owned tables
- test cross-organization reads and writes against PostgreSQL
- disable automatic table exposure and expose no application tables through
  Supabase Data API unless there is a deliberate client-side use case
- add invitations, password recovery, session revocation, and organization switching
- add organization-scoped AUT1 service accounts with named permissions,
  expiration, rotation, last-use evidence, immediate revocation, signed webhook
  secrets, timestamp windows, and replay protection; never expose database or
  provider credentials to an automation client

Automatic RLS is not a substitute for this phase. It affects new tables only
and does not define the required policies or application session context.

### PR3: live provider truth

- configure and validate rankings
- connect Google Business Profile and Search Console
- validate supported Google local-post and media actions on one owned profile,
  then a dry-run and bounded live G1.4B campaign across a reviewed location
  group before enabling Growth or Enterprise fleet dispatch
- connect the approved website analytics/form-event source
- keep call-tracking, CRM, job-management, booked-job, payment, revenue, and
  sales-attribution connections out of Growth G1
- implement local, review, citation, and authority production adapters
- configure SMTP and durable report storage
- expose provider setup and health to organization owners
- record provider-reported currency cost and credential ownership for every paid operation
- prevent platform-paid tasks from dispatching after the organization's hard allowance is exhausted

### PR4: workflow closure

Prove one complete production journey:

```text
create organization
  -> add business
  -> crawl website
  -> collect rankings and local data
  -> generate recommendation
  -> approve and dry-run execution
  -> record outcome
  -> generate and deliver report
```

Then complete or deliberately hide Settings, Locations, Content, Authority,
and agency portfolio features based on launch scope.

### PR5: release hardening

Implementation status (2026-08-21):

- The first browser-driven launch smoke is implemented. It validates the public
  sign-in form, performs a non-mutating owner sign-in, confirms active-location
  context, opens Overview and Reports, and checks the complete categorized
  navigation at desktop and mobile widths.
- The manual GitHub workflow installs isolated Chromium, requires protected
  production-environment credentials, is fixed to the InsightOS production
  hostname and `main` branch, exposes credentials only to the test step, revokes
  its sign-in afterward, and never retains production screenshots, traces, or
  video or raw console text. The production environment must still be restricted
  to `main` with an independent reviewer, and the credentials must belong only
  to a least-privileged synthetic tenant before its first automated run.
  That tenant must contain two locations, comparable saved reports, and bounded
  synthetic Overview metrics so the smoke proves live API-backed content.
  Local public-path proof passes. A manual authenticated production check on
  2026-08-21 also confirmed Overview, the active-location control, Reports,
  all five navigation groups, the absence of a collapsed `More tools` group,
  mobile navigation at 390×844, and zero captured console warnings or errors.
  The check performed no customer-data mutation and restored the normal
  viewport afterward. The automated GitHub receipt remains pending until the
  smoke account secrets are configured and the workflow runs.

- PostgreSQL integration CI
- eliminate SQLite cross-session write-lock stalls in campaign-cycle tests
- RLS isolation tests
- Playwright critical-journey tests
- Vercel production smoke tests
- backup and restore drill
- backward-compatible migration and deployment sequencing
- alerting for dead-letter jobs, stale leases, provider failures, and delivery failures
- AUT1 contract tests for webhook signatures, duplicate delivery,
  idempotency-key reuse, revoked credentials, wrong-location access, privacy
  field allow-lists, entitlement denial, approval bypass attempts, and
  destination SSRF defenses

### PR6: final UI/UX revamp

The visual redesign remains the final implementation phase:

- settle information architecture from proven workflows
- split monolithic route pages into tested feature components
- establish final design tokens and interaction patterns
- complete responsive and accessibility work
- add visual regression coverage
- perform final copy, onboarding, and trust-state polish

The final redesign should present verified product behavior. It should not hide
or compensate for missing providers, non-durable jobs, or ambiguous outcomes.
