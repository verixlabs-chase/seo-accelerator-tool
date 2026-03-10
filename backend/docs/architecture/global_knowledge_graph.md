# Global Knowledge Graph

Audit prerequisite: Future system audits must read the architecture documents in `backend/docs/architecture/` before performing code analysis.

## Purpose
The global knowledge graph is the authoritative persistent store for learning relationships across policies, features, outcomes, industries, and policy evolution lineage.

## Node types
- `feature`
- `policy`
- `outcome`
- `industry`

## Edge types
- `policy_feature`
- `feature_outcome`
- `policy_outcome`
- `policy_policy`

## Event pipeline
```text
experiment.completed
  -> causal learning validates payload
  -> update_engine upserts policy->feature, feature->outcome, policy->outcome
  -> strategy evolution reads graph candidates
  -> update_engine upserts policy->policy lineage
```

## Learning loop
```text
experiment outcome
  -> knowledge graph updates
  -> portfolio consults graph
  -> strong policies evolve
  -> policy->policy lineage recorded
  -> new experiments launched
```

## Responsibilities
- `knowledge_graph/query_engine.py` owns all graph reads
- `knowledge_graph/update_engine.py` owns all graph writes
- causal learning writes graph evidence
- portfolio reads graph preferences before allocating
- strategy evolution records parent->child policy lineage

## Safety constraints
- graph identities are unique by `(source_node_id, target_node_id, edge_type, industry)`
- graph writes must go through `update_engine.py`
- direct `KnowledgeEdge` inserts outside `knowledge_graph/` are architecture violations
