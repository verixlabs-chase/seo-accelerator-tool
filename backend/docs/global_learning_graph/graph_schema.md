# Graph Schema

## Node model
Common node fields:
- node_id: globally unique stable identifier.
- node_type: campaign | industry | feature | pattern | strategy | outcome.
- name: canonical display name.
- attributes: typed key-value payload.
- created_at: first observed timestamp.
- updated_at: last updated timestamp.
- status: active | deprecated.

## Edge model
Common edge fields:
- edge_id: deterministic hash of source, relation, target, cohort scope.
- source_node_id
- target_node_id
- edge_type: improves | correlates_with | causes | derived_from.

Required edge metadata:
- confidence: float [0,1], confidence of relation validity.
- support_count: integer, number of supporting observations.
- outcome_strength: float, signed magnitude of observed impact.
- cohort_context: object with industry/segment/channel/geo/time-window.
- timestamp: last evidence timestamp.
- model_version: producer model version that emitted or updated relation.

Optional edge metadata:
- decay_factor
- sample_size
- p_value_or_equivalent
- source_event_ids

## Temporal behavior
- Edges are append-updated with rolling aggregates.
- Historical snapshots are retained for audit and replay.
- Confidence can decay over time without fresh evidence.

## Identity rules
- campaign nodes map 1:1 with campaign UUID.
- industry nodes map to controlled taxonomy.
- feature/pattern/strategy/outcome use canonical normalized keys.

## Consistency rules
- No edge without required metadata.
- No duplicate active edge for same (source, edge_type, target, cohort_context hash).
- Write operations are idempotent.
