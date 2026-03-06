# Governance and Quality Controls

## Goals
- Prevent low-quality or biased relationships from driving decisions.
- Ensure explainability and reproducibility of graph-derived intelligence.

## Controls
- Schema validation: reject edges missing required metadata.
- Confidence gating: enforce edge-type minimum thresholds.
- Support thresholds: require minimum sample support before activation.
- Freshness control: decay or deactivate stale edges.
- Drift monitoring: compare recent outcome distribution vs historical baseline.
- Lineage enforcement: every edge links to source evidence events.

## Data quality checks
- Node key normalization and deduplication.
- Cohort context completeness validation.
- Model version compatibility checks.
- Outlier detection for abnormal outcome_strength updates.

## Safety policies
- No causes edge without high-confidence evidence and causal tag.
- Industry transfer limits when cohort mismatch exceeds threshold.
- Automatic fallback to campaign-local logic on confidence collapse.

## Auditability
- Persist per-update decision logs.
- Snapshot edge states for replay and incident analysis.
- Include evidence set in every high-impact query response.

## Monitoring KPIs
- Edge acceptance/rejection rates.
- Graph freshness index.
- Confidence drift rate.
- Graph query utilization by consumer.
- Uplift from graph-informed recommendations.
