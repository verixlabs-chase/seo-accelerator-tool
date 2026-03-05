# Domain Definitions

## SEO signal
Description: raw or normalized measurement captured at a specific observation time.
Example: technical_issue_count equals 42.
Appears in: signal extraction output and temporal signal store.

## Feature
Description: derived value computed from one or more signals over a time window.
Example: ranking_velocity_14d equals 0.22.
Appears in: feature store and policy engine inputs.

## Pattern
Description: repeatable relation between features and outcomes.
Example: low internal link ratio and low content growth often precede ranking stagnation.
Appears in: pattern engine and pattern evidence records.

## Recommendation
Description: concrete strategy action proposed by policy.
Example: prioritize internal linking remediation for top landing pages.
Appears in: recommendation engine output and lifecycle workflow.

## Strategy
Description: ordered set of recommendations for a campaign objective and phase.
Example: 30 day recovery strategy with technical first actions.
Appears in: campaign strategy payloads and automation planning.

## Automation action
Description: executable action produced from approved recommendations.
Example: schedule crawl QA run and create content refresh tasks.
Appears in: automation engine and automation events.

## Outcome
Description: measured post action change in business and SEO metrics.
Example: ctr increase and avg position improvement in evaluation window.
Appears in: outcome tracking system.

## Baseline window
Description: pre execution period used as reference.
Example: 28 days before recommendation execution.
Appears in: outcome comparator.

## Evaluation window
Description: post execution period used to compute effect.
Example: day 7 to day 35 after action completion.
Appears in: reward computation.

## Reward signal
Description: bounded effectiveness value used by learning updater.
Example: plus 0.31 from weighted metric deltas.
Appears in: feedback loop and strategy effectiveness tables.

## Learning feedback
Description: persisted update to pattern confidence, policy weights, or recommendation priors.
Example: reduce confidence prior for underperforming pattern by 0.08.
Appears in: learning feedback model and policy bundle versioning.

## Confidence score
Description: expected probability like measure of positive impact.
Example: confidence_score equals 0.79.
Appears in: recommendation payload and transition guardrails.

## Risk tier
Description: operational risk class that controls automation eligibility.
Example: risk tier 3 requires manual validation.
Appears in: recommendation lifecycle and automation gating.

## Evidence
Description: structured facts proving why a recommendation was generated.
Example: feature values, triggered rules, window references.
Appears in: recommendation evidence and audit exports.

## Policy bundle
Description: versioned package of thresholds, weights, and tie break rules.
Example: policy bundle v2026_03_01.
Appears in: recommendation metadata and replay governance.
