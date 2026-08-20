# Paid Launch Closeout

This runbook is the operator procedure for an InsightOS paid release. It does
not make a release ready by existing. The platform-owner readiness board must
contain current evidence, and the current release must have an append-only
owner decision.

## Required roles

Record the person currently filling each role in the internal release record.
A role without a named, reachable person is a launch blocker.

| Role | Owns |
| --- | --- |
| Release owner | final evidence review and go/no-go decision |
| Support owner | customer intake, response targets, and handoff |
| Incident commander | severity, investigation owner, and customer updates |
| Recovery owner | rollback execution and verification |
| Billing owner | checkout, webhook, portal, and payment recovery |
| Provider owner | Google, data-source, workflow-tool, and quota escalation |

Never place passwords, signing secrets, webhook addresses, provider response
bodies, customer page content, or supplier-account identifiers in a readiness
receipt. Use an internal ticket or receipt reference.

## Closeout sequence

1. Deploy the release through the maintained deployment procedure.
2. Confirm production runtime safeguards, tenant isolation, rate limits,
   billing configuration, durable artifact storage, provider health, freshness,
   and the support queue on `/platform/readiness`.
3. Open `/platform/experience`. Complete all 19 customer routes on desktop and
   mobile, and record five distinct passing non-technical sessions. Resolve and
   repeat every failed, missing, or expired review.
4. Run the five manual proof groups below and append each result only after its
   structured evidence is current. A failed test
   is recorded as failed; it is not omitted or rewritten.
5. Resolve every blocker and repeat any failed or expired proof.
6. Re-open the board after the final write. Confirm every gate is passing and
   the board says `Ready for owner decision`.
7. The release owner records `Go` or `No go` with the current evidence,
   limitations, support owner, and rollback owner confirmations.
8. Re-open the board. Only a current recorded `Go` authorizes launch. Any later
   evidence change supersedes the decision and requires a new review.

## Proof group 1: paid customer journeys

Owner: Release owner

- First complete the desktop/mobile route matrix on `/platform/experience`.
  Review the normal, loading, empty, error, recovery, and navigation behavior
  for every listed customer page. A desktop pass never substitutes for mobile,
  and an automated test never substitutes for this production review.

- Complete a new Solo workspace from sign-in through location, Google Search
  connection, mandatory baseline, first next action, and report download.
- Complete checkout return, saved subscription confirmation, billing portal,
  payment failure recovery, cancellation, and safe re-subscription using the
  approved billing environment.
- Confirm sign-out and remote session removal from another browser.
- Confirm a workflow destination is not called connected merely because its
  receiving address was saved. Record signed-test and first-real-event truth
  separately for every advertised tool.

Record under `Paid customer journeys` using the internal release receipt.

## Proof group 2: recovery and rollback drills

Owners: Recovery owner and Billing owner

- Run the deployment rollback procedure in
  `docs/platform/runbooks/deployment_runbook.md`.
- Run worker recovery using `docs/platform/runbooks/worker_recovery.md`.
- Verify a durable report write, authenticated download, checksum failure, and
  restore without exposing its storage path to a customer.
- Interrupt and recover a WordPress change using its saved preview, approval,
  public-page proof, and rollback record. Do not create a new mutation merely
  to make the drill pass.
- Run billing recovery using `docs/operations/stripe-billing-runbook.md`.
- Exercise export, recoverable closure, and irreversible deletion as separate
  procedures with the documented confirmation boundaries.

Record under `Recovery and rollback drills`.

## Proof group 3: incident and status communication

Owners: Incident commander and Support owner

- Follow `docs/platform/runbooks/incident_response.md` using a harmless test
  incident or a sanitized completed incident.
- Assign severity, incident commander, investigation owner, affected customer
  scope, next-update time, recovery path, and corrective-action owner.
- Send the test message through the actual supported customer communication
  path. Publish the investigating update through `/platform/readiness`, verify
  it appears inside a signed-in customer product page, then publish and verify
  the resolution update. Earlier history must remain visible to platform staff.
- Use only customer-facing area names and plain impact language. Never paste a
  provider name, raw error, customer identifier, link, credential, or internal
  response body into the customer status update.
- Confirm no overdue support request remains and response targets match the
  customer plan.

Record under `Incident and status communication`.

## Proof group 4: non-technical first use

Owner: Release owner

- Moderate at least five representative home-service or local-business owners.
- Do not operate the product for them or teach OAuth, analytics jargon,
  webhooks, signatures, schemas, provider ledgers, or internal SEO terms.
- Require each participant to connect Google Search, understand optional
  analytics, add a location, read the baseline, find the next action, connect
  one workflow tool, manage billing, and remove another signed-in browser.
- Record each observed confusion, severity, owner, resolution, and retest.
- Append each participant result on `/platform/experience` under a unique opaque
  alias such as `UX-0001`. Never store a participant name, email, recording,
  link, or provider response in the platform ledger.

Record under `Non-technical first-use proof` only after every launch-blocking
confusion is closed and the structured board shows five current passing
participants. The manual proof must be newer than the latest session.

## Proof group 5: sales claims and limitations

Owners: Release owner and Support owner

- Compare pricing, demos, onboarding, Help, Settings, and sales language with
  current production behavior.
- Open `/platform/capabilities`. Every marketed capability must have a current
  production-proven, limited, or unavailable receipt. Plan inclusion alone is
  not evidence that the capability works in production.
- Copy every saved customer limitation into the relevant pricing, demo, Help,
  and support path before recording this review. Repeat the review whenever a
  capability receipt changes; an older review does not cover a newer matrix.
- Mark fixture-only, synthetic, disabled, approval-pending, unconnected,
  unavailable, stale, and partially measured capabilities accurately.
- Confirm the plan allowance, workflow authority, WordPress authority,
  Business Profile authority, AI visibility, private-model, and client-report
  boundaries for each advertised tier.
- Publish the current known-limitations list to the supported customer path.

Record under `Sales claims and known limitations`.

## Immediate no-go conditions

- Any readiness gate is blocking, attention, needs live proof, or expired.
- Billing lifecycle proof, production tenant isolation, or durable report
  retrieval is not current.
- A paid provider or workflow is advertised without current provider-owned
  evidence and a supported recovery route.
- A critical support request is overdue or the incident, support, or rollback
  role is unnamed.
- Moderated first-use launch blockers remain open.
- The latest owner decision is absent, `No go`, or superseded by newer evidence.

## After launch

- Watch provider health, support response targets, data freshness, billing
  webhooks, durable jobs, and customer-facing connection truth.
- Record failures as new evidence. Do not edit or delete a prior receipt.
- Re-run affected proofs after a material provider, billing, data, workflow,
  WordPress, security, or customer-visible contract change.
- A changed readiness basis supersedes the prior decision. Return to the
  closeout sequence before expanding availability.
