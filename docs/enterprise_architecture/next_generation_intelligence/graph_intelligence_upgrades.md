# Graph Intelligence Upgrades

## Evolution goals
Extend the Global Learning Graph from associative memory to causal and rule-aware intelligence.

## New graph entities
- Causal nodes: represent causal assertions with effect metadata.
- Rule nodes: represent active causal rules and lifecycle state.
- Effectiveness nodes: track strategy performance by cohort/time.

## New graph capabilities
- Industry cohort learning with temporal confidence decay.
- Rule-to-strategy and rule-to-outcome linking.
- Causal conflict detection and resolution policies.

## Write-path upgrades
- Streamed edge updates from outcomes and simulations.
- Periodic consolidation jobs to merge redundant evidence.
- Snapshotting for reproducible replay and audits.

## Query-path upgrades
- Multi-hop retrieval (campaign -> pattern -> rule -> strategy -> outcome).
- Counterfactual context queries for strategy comparison.
- Explainability payloads with lineage and confidence factors.
