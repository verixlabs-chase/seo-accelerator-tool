# Governed learning-rule review

## Purpose

I2E compares the rule InsightOS currently uses to decide when saved outcomes
are mature enough for learning with a stricter proposed rule. It does not
change recommendation order, forecasts, a website, or a Google Business
Profile. It creates a sealed review artifact for a later activation sprint.

The first policy family is deliberately narrow:

`action_learning_eligibility`

It answers one question: do enough independent, owner-approved results exist
for a matching action and measurement before that evidence may support a future
rule change?

## Why this is not a priority-weight update

The current product does not yet retain the counterfactual routing evidence
needed to prove that a different recommendation weight would have produced a
better result. Changing a weight and replaying only the resulting number would
be a cosmetic comparison, not outcome learning. I2E therefore governs evidence
eligibility first and leaves recommendation-weight and forecast-model changes
for later policy families with appropriate replay data.

## Independent evidence

Only distinct completed action measurements may count. Every counted result
must:

- belong to the same tenant, organization, campaign, action, metric, and
  measurement-contract version;
- have a saved before-and-after result that remains comparable;
- have an explicit owner decision to include it; and
- retain its own measurement identity and observation time.

Guardrail polling is safety monitoring, not a new experiment unit. Rechecking
the same result never increases the policy sample size.

## Current and proposed rules

The current rule represents the existing review-readiness threshold: five
matching owner-included results.

The first proposed rule is more conservative. It requires:

- a successfully completed governed monitoring protocol;
- at least the controlled plan's saved minimum sample, with an absolute floor
  of ten independent results;
- at least a 60% measured-improvement ratio;
- no more than a 25% measured-worse ratio; and
- a 90% Wilson lower confidence bound of at least 35% for the improvement
  proportion.

These thresholds are product governance defaults, not claims about Google's
ranking algorithm and not proof that the tested work caused the outcomes.

## Deterministic replay

Replay orders the minimized evidence deterministically and evaluates cumulative
prefixes against both frozen rule versions. The report preserves:

- the exact candidate and evidence hashes;
- the number of distinct included results;
- improved, unchanged, and worse counts and ratios;
- Wilson confidence bounds;
- each point where the current and proposed eligibility decisions differ;
- final eligibility under both rules; and
- any blocker that prevents review.

Running replay again with the same candidate and evidence must produce the same
artifact hash. New, removed, or reclassified evidence requires a new replay and
cannot silently inherit an older decision.

## Human decision and future activation

An owner may approve a passed proposal **for future activation review**, reject
it, or cancel it. Approval requires explicit confirmation that the comparison
was reviewed, is not active, and is not causal proof.

The decision record is final and append-only. I2E has no activation, promotion,
assignment, execution, publishing, WordPress, Google Business Profile, or
production rollback endpoint. A later sprint must add a separate activation
boundary, shadow monitoring, pause, and rollback before any proposed rule can
affect live recommendations or forecasts.

## Security and audit boundaries

Candidates, replay reports, and decisions carry tenant, organization, campaign,
and location scope. PostgreSQL row-level security enforces tenant and
organization context. Immutable and append-only database protections prevent
ordinary application sessions from rewriting sealed evidence or decisions.

Audit records contain governed IDs, hashes, states, counts, and acknowledgement
flags. They do not contain owner notes, raw evidence text, or another tenant's
identifiers.

## Deliberately disabled

- automatic policy activation;
- live policy-weight updates;
- legacy experiment or assignment creation;
- recommendation or forecast mutation;
- website or profile changes;
- publishing or WordPress execution;
- automatic rollback; and
- causal claims from observational evidence.
