# Next-Generation Intelligence Architecture

## Architectural principles
- Event-first, asynchronous, and horizontally scalable.
- Deterministic decision traces for every automated action.
- Separation of online inference paths and offline learning paths.
- Safety and governance as hard gates, not advisory checks.

## Reference architecture
~~~text
+----------------------- Ingestion Layer -----------------------+
| Crawlers | Rank Feeds | GBP | Content | User Signals         |
+------------------------------+--------------------------------+
                               v
+----------------------- Event Streaming -----------------------+
| Topic partitions: signal, feature, pattern, simulation, ...   |
+------------------------------+--------------------------------+
                               v
+----------------------- Compute Fabric ------------------------+
| Feature workers | Pattern workers | Recommendation workers     |
| Simulation workers | Outcome workers | Graph update workers     |
+------------------------------+--------------------------------+
                               v
+------------------------- Intelligence Core --------------------+
| Predictive Engine | Causal Rule Engine | Strategy Transfer     |
| Global Learning Graph | Policy Learning | Risk + Guardrails     |
+------------------------------+--------------------------------+
                               v
+---------------------- Serving + Control Plane ----------------+
| Recommendation API | Orchestration API | Observability | Admin |
+---------------------------------------------------------------+
~~~

## Logical domains
- Online decisioning domain: low-latency recommendation and risk gating.
- Learning domain: model retraining, rule discovery, graph consolidation.
- Operations domain: queue management, autoscaling, SLO enforcement.
