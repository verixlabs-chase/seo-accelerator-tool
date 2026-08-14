# Governed controlled-test monitoring

## Purpose

The I2D monitoring protocol watches a previously approved controlled-test
design without turning the intelligence layer into an unreviewed publishing
system. It answers four questions with saved evidence:

1. What exact result and safety measurements did we start from?
2. Who separately authorized the observation protocol?
3. Did a fresh, matching measurement pass or hit a stop rule?
4. If the work was stopped, was the approved starting state restored and
   verified?

## State flow

`prepared -> authorized -> monitoring -> completed`

A safety issue or owner decision branches the flow to:

`monitoring -> stop_required -> rollback_pending -> rollback_verified`

An owner may also stop a monitoring protocol directly, which moves it to
`rollback_pending`.

## Frozen evidence

Preparing a protocol requires an approved `GovernedExperimentPlan` and an
available current primary measurement. Every optional protected measurement
must also be available. InsightOS freezes:

- the approved plan ID and artifact hash;
- the primary and protected starting measurements and their scopes;
- the mandatory stop rules;
- the owner-reviewed undo steps;
- the monitoring protocol version and deterministic artifact hash; and
- the current customer-facing Insight Credit state.

The approved design must still exist, remain approved, and retain the same hash
when the second authorization is recorded.

## Second authorization

The owner must explicitly confirm that:

- the frozen plan and starting measurement were reviewed;
- the undo steps can be completed if a stop rule is hit; and
- authorization only enables monitoring and does not make a change.

Starting monitoring then requires an evidence reference for the separately
approved change, such as a WordPress revision, change ticket, or profile update
record. The protocol stores that reference but does not call a mutation,
publishing, WordPress, or Google Business Profile endpoint.

## Deterministic checks

Each requested check reads the same governed metric definitions used by action
measurement. The comparison is valid only when the provider, entity scope,
scope key, measurement window, and governed improvement direction still match.

- No newer matching measurement: remain in `waiting_for_fresh_data`.
- Missing, incomparable, or directionless measurement: `data_quality_loss`.
- Primary result worse than its frozen starting point:
  `primary_metric_regression`.
- Protected result worse than its frozen starting point:
  `protected_metric_regression`.
- No remaining allowance for optional paid checks: `allowance_exhausted`.
- A fresh passing measurement after the observation due date: `completed`.

Every check is append-only and stores its captured metrics, customer-facing
credit summary, triggered rules, check time, checker, and deterministic hash.
The result is an experiment observation; it is not stored or presented as
automatic causal proof.

## Stop and rollback

The owner can stop monitoring at any time. A stop records a governed reason and
opens the frozen undo checklist. Rollback verification requires both:

- confirmation that every saved undo step was completed; and
- at least one evidence reference showing the original state was restored.

I2D records verification. It does not perform a rollback automatically.

## Security and isolation

Protocols and checks carry tenant, organization, and campaign scope. Service
queries require all three. PostgreSQL row-level security requires the active
tenant and organization context, with the existing platform-access exception
for governed system work. Audit events intentionally record IDs, hashes,
states, rule codes, and evidence counts rather than owner-entered notes or
evidence text.

## Deliberately disabled

- automatic website or profile changes;
- automatic publishing;
- legacy experiment assignments;
- automatic rollback;
- automatic policy or forecast-model activation; and
- unattended scheduled guardrail checks.

Those capabilities require later, separately reviewed gates. The next I2 slice
should define champion/challenger policy artifacts and the evidence required to
promote, monitor, pause, and reverse them without self-activation.
