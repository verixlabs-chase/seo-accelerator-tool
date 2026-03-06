# Graph Update Pipeline

## System definition
The update pipeline converts existing intelligence outputs into validated graph relationships with metadata and temporal updates.

## Input sources
- Recommendation outcomes from outcome tracking.
- Digital twin simulation predictions and calibration deltas.
- Pattern detection events and significance updates.

## Stages
1. Event capture
- Collect normalized events from existing pipeline boundaries.

2. Canonical mapping
- Resolve entity keys into node IDs.
- Ensure node existence (upsert if missing).

3. Relationship derivation
- Apply typed derivation rules per event class.
- Propose candidate edges with provisional metadata.

4. Evidence scoring
- Compute confidence, support_count, and outcome_strength.
- Attach cohort_context, timestamp, model_version.

5. Governance validation
- Enforce required metadata and quality thresholds.
- Reject or quarantine low-quality edges.

6. Idempotent upsert
- Merge with existing edge, update aggregates, retain history snapshot.

7. Post-update metrics
- Emit update stats to metrics engine for observability.

## Relationship creation rules by source
### Recommendation outcomes
- strategy -> outcome (improves|causes) from realized KPI deltas.
- campaign -> outcome (derived_from) for campaign-scoped attribution lineage.

### Digital twin simulations
- strategy -> outcome (correlates_with) from predicted effect curves prior to execution.
- campaign -> strategy (derived_from) for simulation provenance.

### Pattern detection
- feature -> pattern (derived_from) lineage.
- pattern -> strategy (correlates_with|improves) when repeated evidence exists.

## Freshness and decay
- Apply confidence decay when evidence is stale.
- Promote or demote edges as new evidence accumulates.
