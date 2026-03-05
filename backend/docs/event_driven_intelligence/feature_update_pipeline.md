# Feature Update Pipeline

## System definition
Deterministic feature recomputation pipeline driven by signal change events.

## Purpose
Recompute only impacted features and avoid full campaign feature refresh.

## Inputs
- signal.updated event payload
- temporal signal snapshots
- feature dependency map

## Outputs
- updated feature snapshots
- feature.updated event

## Data models
- FeatureDependencyMap with feature_name and required_signals
- FeatureSnapshot with campaign_id, feature_name, value, computed_at, version_hash

## Failure modes
- missing source signal data
- stale dependency map
- write conflict on snapshot persistence

## Scaling considerations
- cache dependency map in worker memory
- batch feature writes
- skip no change updates

## Example code snippet
    def recompute_features_for_change(campaign_id, changed_signals):
        impacted = dependency_map_for_signals(changed_signals)
        updates = {}
        for feature_name in impacted:
            updates[feature_name] = compute_feature(feature_name, campaign_id)
        persist_feature_updates(campaign_id, updates)
        publish_event('feature.updated', {
            'campaign_id': campaign_id,
            'changed_features': list(updates.keys())
        })

## Integration points
- app intelligence feature_store
- app intelligence signal_assembler
- app intelligence pattern engines

