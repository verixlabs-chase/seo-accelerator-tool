# Integration with Intelligence Pipeline

## Integration objective
Integrate GLG as a cross-campaign memory and retrieval layer without disrupting existing deterministic pipeline stages.

## Integration points
### Signal pipeline
- Supplies campaign/industry context signals for node enrichment.
- Receives optional graph-derived priors for cold-start weighting.

### Feature store
- Emits feature lineage inputs for derived_from edges.
- Consumes graph priors to initialize sparse campaign features.

### Pattern engine
- Publishes detected patterns and significance updates.
- Queries GLG for industry-relevant prior patterns before scoring.

### Recommendation engine
- Queries historically effective strategies/actions by cohort.
- Uses graph confidence/support as a ranking feature.

### Digital twin simulations
- Uses GLG evidence as prior constraints on simulation parameters.
- Emits calibration feedback to reweight graph confidence.

### Policy learning system
- Reads cross-campaign outcomes for policy updates.
- Writes policy-derived influence/improvement adjustments.

### Metrics engine
- Ingests GLG quality and usage metrics.
- Monitors impact of graph-informed decisions vs baseline.

## Contract boundaries
- GLG is advisory in initial rollout; governance gate remains final authority.
- All graph-enriched decisions require traceable evidence payloads.

## Rollout pattern
1. Shadow mode retrieval.
2. Read-only ranking feature contribution.
3. Controlled influence on strategy ranking.
4. Full production integration with guardrails.
