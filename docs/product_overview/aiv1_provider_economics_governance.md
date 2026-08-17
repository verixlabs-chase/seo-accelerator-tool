# AIV1 Provider and Economics Governance

## Status and authority

This document governs provider integration, evidence reproducibility, and usage
economics for **AIV1 - AI Search Visibility and Entity Intelligence**. It
narrows the broader product specification in
`ai_visibility_intelligence_engine.md`; where the documents differ on live
collection or commercial readiness, this document controls.

**Current slice: the AIV1-A foundation is implemented locally.** It includes
candidate-only immutable registries, deterministic question preparation,
provider-neutral dormant run/evidence storage, an honest beta workspace, a
fail-closed non-executing collection preview, and safety tests. Sections 1-7
define the target contract for the full AIV1 release; fields and checks tied to
live supplier work are requirements for AIV1-B/AIV1-C, not claims that live
collection is already implemented. Live collection and customer-visible engine
activation remain intentionally unavailable.

## 1. Provider-neutral version contracts

The customer product must depend on stable internal contracts, never on a
supplier's names or response shape.

An immutable **engine version** records:

- stable engine key, version, display name, and lifecycle state
  (`candidate`, `active`, or `retired`);
- supported geography, language, device, and personalization policy;
- supported evidence facts and known collection limits;
- effective and superseded timestamps, definition hash, QA approval, and
  whether the version is customer-visible.

Before live provider evaluation or collection, an immutable **provider contract
version** must record:

- internal provider key, contract version, capability, and operation;
- request and response schema versions;
- mapping to one or more engine versions;
- synchronous or submit/poll behavior;
- parser and normalizer versions, field guarantees, retention limits, and
  billable unit compatibility;
- definition hash, lifecycle state, production-proof reference, and explicit
  human approval.

Changing an existing immutable version is prohibited. A changed engine,
provider response, parser, normalizer, or collection method creates a new
version and a clearly labeled comparison boundary. Candidate versions cannot
activate themselves.

## 2. Reproducible collection record

This is the required AIV1-B/AIV1-C live-execution contract. AIV1-A stores the
provider-neutral identity, comparison, parser/normalizer, evidence, and cost
provenance references needed to make later execution fail closed, but it does
not dispatch work and does not yet claim the full live telemetry below.

Before customer collection is enabled, every live collection run and
observation must preserve enough context to reproduce or explain the result:

- tenant, organization, campaign, location, and authorized credential owner;
- engine key/version and provider contract/version;
- exact question, question hash, frozen prompt-set key/version, and prompt-set
  hash;
- frozen service catalog, service-area, target-entity, and competitor snapshot
  identifiers and hashes;
- provider geography identifier plus an owner-readable place, country,
  language, device, and personalization policy;
- collection method/model when supplied, parser version, and normalizer
  version;
- requested, submitted, collected, and completed timestamps;
- internal run ID and provider task/request IDs;
- raw-response hash, encrypted/private object reference, allowed retention
  expiry, normalized-result hash, and evidence reference;
- price-card version, cost reservation ID, credential owner, estimated cost,
  reconciled cost, requested check count, and collected observation count;
- run state (`queued`, `running`, `partial`, `succeeded`, `unsupported`,
  `unavailable`, or `failed`), failure classification, and coverage gap;
- prior comparable run ID and comparison-scope hash.

A changed question, location context, engine mapping, provider contract,
collection method, parser, or normalizer starts a new comparison version. The
product must not draw a continuous trend line across that boundary without an
explicit discontinuity label.

## 3. Independent truth facts

Provider output is normalized into independent observable facts:

- the business was **mentioned**;
- the business was **recommended**;
- the business or one of its pages was **cited as a source**;
- a business page was **linked**;
- prominence or order, only when the approved contract supplies it;
- competitors observed, URLs observed, and the allowed excerpt or evidence
  reference.

One fact never proves another. In particular, a mention is not a
recommendation, a citation is not necessarily a link, and absence from one
sample is not proof of universal absence. AIV1 must not convert the existing
entity-overlap score or a documentation-only readiness score into evidence of
AI-search visibility.

Initial customer metrics should be transparent fact rates with their sample
sizes. A composite score is prohibited until its governed definition,
calibration evidence, and customer interpretation have passed separate review.

## 4. Unavailable is not zero

`unsupported`, `unavailable`, `partial`, and `failed` observations are excluded
from the denominator for appearance rates and comparison math. They must remain
visible as coverage gaps. Only a successfully collected, contract-valid answer
that did not contain a fact may contribute a factual `false` or zero.

An unavailable engine, missing field, expired raw artifact, parser rejection,
or provider outage must never be normalized into "not mentioned," zero
visibility, or a negative trend.

## 5. Supplier redaction and data handling

Customer APIs, UI, exports, reports, notifications, and AI explanations use
engine and evidence language, not supplier branding. They must omit internal
provider keys, supplier product names, endpoints, task IDs, raw payloads,
credentials, supplier error bodies, price cards, and internal cost details.

Supplier identity and raw evidence are restricted to authorized platform
operations, audits, and support. Logs and errors must be sanitized before
persistence. Raw evidence must follow the provider's data rights and retention
terms; a hash is not permission to retain the source indefinitely.

## 6. Two-stage allowance and cost gate

AIV1-A exposes only a side-effect-free preview whose pricing and usage gates
remain blocked. It does not create work, reserve credits, resolve a production
price, or claim that provider capability/operation/billable-unit matching is
complete. AIV1-B must prove those mappings and observed prices before AIV1-C
can implement the executable gate below.

Every run is rejected before provider dispatch unless both gates pass:

1. **Product-volume gate.** Freeze the prompt set and calculate observations as
   questions x engines x geographies x devices. Enforce plan, manual-run,
   schedule, rate, concurrency, and abuse limits for platform and customer-owned
   credentials.
2. **Platform-economics gate.** Resolve an approved, observed price-card version;
   estimate the conservative maximum cost; preview customer credits; lock the
   organization; and reserve credits and cost before creating provider work.

Polling an accepted provider task never creates another charge. Successful and
partial results reconcile against actual billable work. Confirmed terminal
failures release the reservation. When supplier acceptance or billing is
uncertain, the reservation remains until reconciliation rather than assuming
the call was free.

Customer-owned credentials can be excluded from platform COGS and Insight
Credit charging only when the credential policy says so. They remain subject
to product volume, rate, concurrency, and abuse limits.

**No guessed price card or arbitrary commercial allowance may be seeded.** A
price card must be derived from an approved live evaluation, record its source
and effective time, and match the provider contract's billable unit.

Before customer release, the heavy-but-permitted usage case for every plan must
demonstrate at least an **85% software-usage gross margin** after provider,
model, storage, queue, map, and other variable software costs. If it does not,
reduce included volume, change cadence, improve unit cost, or reprice before
release. Average-user economics cannot substitute for this boundary test.

## 7. Durable submit/poll requirements

Live collection uses a durable `ai_visibility.collect` job with a
tenant-inclusive idempotency key and a frozen run definition. The provider
adapter exposes `submit(request)` and `collect(submission)`; a synchronous
provider may return a completed submission, while an asynchronous provider is
polled through the same state machine.

The job must provide leases, bounded polling, retry classification,
dead-letter handling, partial persistence, terminal cost reconciliation, and
recovery after worker loss. A retry reuses the run ID, provider task ID, and
reservation. It may resubmit only when evidence proves the supplier did not
accept the original request. Duplicate dispatch, duplicate charging, and
unbounded polling are release blockers.

## 8. Rollout gates

### AIV1-A - Provider-neutral foundation (implemented locally)

Allowed work:

- immutable engine and provider-contract registries;
- frozen prompt sets plus dormant provider-neutral collection-run,
  observation, and comparison-scope storage;
- a location-scoped beta workspace that can prepare saved questions and show
  truthful setup, stale, unavailable, and not-measured states without running
  a paid check;
- provider-neutral API shapes, a side-effect-free collection preview, RLS,
  tenant isolation, immutability, denominator, redaction, idempotency, and
  economics tests.

Provider actions that must remain disabled in AIV1-A:

- reading platform or customer-owned credentials for AIV1 dispatch;
- live submit, poll, refresh, schedule, webhook, or raw-result ingestion;
- activating or showing a customer-visible engine;
- customer manual runs, recurring runs, reports, alerts, recommendations, or
  claims based on provider output;
- reserving or decrementing credits from an unverified price;
- seeding a guessed price card or plan allowance;
- using fixture data as production evidence.

### AIV1-B - Operator-only live evaluation (later)

An authorized platform operator may evaluate a candidate provider only after
credential entitlement, request/response schema, geography/language support,
data rights, retention, billable unit, and expected cost are confirmed. The
evaluation records live contract fixtures, repeated-sample behavior, coverage,
failure modes, latency, and an observed price card. All engines remain
candidate-only and all results remain outside customer dashboards, reports,
actions, schedules, and plan usage.

### AIV1-C - Governed customer collection (later)

Customer collection may start only for individually approved engine and
provider-contract versions after AIV1-B proof, security and RLS review, durable
job proof, supplier-redaction review, allowance and 85% margin proof, and
production QA. It then adds explicit manual/scheduled runs, truthful history,
comparisons, reports, and governed evidence-backed actions. Unsupported engines
remain unavailable rather than simulated.

## 9. Minimum release tests

- Exact request/response fixtures pass for every provider contract version.
- Mapping, parser, normalizer, hashes, and comparison boundaries are
  deterministic.
- Mention, recommendation, citation, and link facts remain independent.
- Missing fields and failed/partial/unsupported checks cannot become zeros.
- Customer surfaces contain no supplier name, raw supplier data, task ID,
  credential, or internal price.
- Cross-tenant reads and mutations fail under API authorization and database
  RLS.
- Run creation is idempotent; lease recovery and polling cannot resubmit or
  charge twice.
- Preview counts and costs equal the frozen dispatched run; reservation,
  reconciliation, and release behavior pass terminal and ambiguous-failure
  cases.
- Platform and customer-owned credentials obey their distinct cost treatment
  while both obey volume and abuse limits.
- Every customer-visible engine has explicit QA approval and production proof.
- The heavy-permitted-use test meets the 85% software-usage margin requirement.
