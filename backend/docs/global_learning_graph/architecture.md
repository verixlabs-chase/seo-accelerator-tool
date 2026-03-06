# Global Learning Graph Architecture

## System definition
GLG is a logical architecture with ingest, graph update, query, and governance layers that connect to existing intelligence components.

## Architecture goals
- Deterministic and explainable relationship construction.
- Incremental updates from existing pipeline outputs.
- Fast query-time retrieval for recommendation and simulation stages.
- Strong controls for data quality, confidence, and drift.

## Layered architecture
~~~text
+--------------------------------------------------------------+
| Intelligence Producers                                       |
| Signal/Feature/Pattern/Recommendation/Simulation/Outcome/PL  |
+-----------------------------+--------------------------------+
                              |
                              v
+--------------------------------------------------------------+
| Graph Update Pipeline                                         |
| Event normalization -> evidence scoring -> edge upsert        |
+-----------------------------+--------------------------------+
                              |
                              v
+--------------------------------------------------------------+
| Global Learning Graph Store                                  |
| Nodes, edges, metadata, temporal snapshots                    |
+-----------------------------+--------------------------------+
                              |
                              v
+--------------------------------------------------------------+
| Query Engine                                                  |
| Similarity, impact retrieval, expected performance estimation |
+-----------------------------+--------------------------------+
                              |
                              v
+--------------------------------------------------------------+
| Consumers                                                     |
| Recommendation engine, digital twin, onboarding intelligence  |
+--------------------------------------------------------------+
~~~

## Core components
- Ingest adapters: convert platform outputs into graph events.
- Relationship builder: derives nodes/edges and computes edge metadata.
- Graph writer: idempotent upserts and temporal versioning.
- Query API: optimized graph retrieval and scoring primitives.
- Governance controls: confidence floors, decay, drift checks, and lineage validation.

## Data contracts
- Every edge carries: confidence, support_count, outcome_strength, cohort_context, timestamp, model_version.
- Every query result includes evidence provenance and freshness.

## Implementation Modules
The first implementation is organized into four modules:

- `app/intelligence/global_graph/graph_schema.py`
  - Defines node/edge enums and dataclasses.
  - Enforces allowed node types: campaign, industry, feature, pattern, strategy, outcome.
  - Enforces allowed edge types: improves, correlates_with, causes, derived_from.
  - Validates required edge metadata fields.

- `app/intelligence/global_graph/graph_store.py`
  - Implements in-memory graph storage for initial rollout.
  - Creates deterministic node and edge IDs.
  - Provides idempotent node and edge upserts.
  - Exposes retrieval primitives used by update and query layers.

- `app/intelligence/global_graph/graph_update_pipeline.py`
  - Ingests intelligence events and maps them to graph relationships.
  - Consumes `PATTERN_DISCOVERED`, `SIMULATION_COMPLETED`, and `OUTCOME_RECORDED`.
  - Applies evidence scoring and metadata enrichment.
  - Performs validated idempotent writes to graph store.

- `app/intelligence/global_graph/graph_query_engine.py`
  - Provides query APIs for campaign-context strategy retrieval.
  - Ranks strategies with confidence, support, outcome strength, and recency.
  - Returns evidence-backed results for recommendation and simulation consumers.

## Implementation Preview
- `graph_schema.py`: enums/dataclasses for node and edge types.
- `graph_store.py`: in-memory graph with deterministic IDs and idempotent node/edge upserts.
- `graph_update_pipeline.py`: ingest from `PATTERN_DISCOVERED`, `SIMULATION_COMPLETED`, `OUTCOME_RECORDED`.
- `graph_query_engine.py`: retrieve strategies relevant to a campaign context.

## Failure modes
- Evidence sparsity in new industries.
- Over-generalization from weak cohort overlap.
- Stale edges if update pipeline lags.

## Non-goals
- Replacing feature store or metrics warehouse.
- Real-time streaming implementation details in this phase.
