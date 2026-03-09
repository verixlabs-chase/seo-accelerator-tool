# Event Catalog

## System definition
This catalog defines canonical intelligence events, their contracts, and required processing guarantees.

## Purpose
Create strict producer and subscriber contracts before implementation.

## Events
1. signal.updated
- Purpose: notify signal changes
- Inputs: temporal signal ingestion completion
- Outputs: feature recomputation trigger
- Payload model: campaign_id, changed_signal_keys, observed_at, snapshot_version

2. feature.updated
- Purpose: notify changed feature values
- Inputs: feature pipeline completion
- Outputs: pattern detection trigger
- Payload model: campaign_id, changed_features, feature_version

3. pattern.discovered
- Purpose: publish detected local or cohort pattern
- Inputs: pattern engine result
- Outputs: recommendation and policy influence updates
- Payload model: campaign_id, pattern_name, pattern_strength, confidence, support_count

4. recommendation.generated
- Purpose: publish recommendation candidates
- Inputs: recommendation generation stage
- Outputs: simulation queue trigger
- Payload model: campaign_id, recommendation_ids, policy_context, priority

5. execution.scheduled
- Purpose: execution queued for approved recommendation
- Inputs: execution scheduler
- Outputs: execution workers

6. execution.completed
- Purpose: execution finished
- Inputs: executor
- Outputs: outcome measurement trigger

7. outcome.recorded
- Purpose: before and after delta available
- Inputs: outcome tracker
- Outputs: policy update and metrics refresh

8. policy.updated
- Purpose: policy weights changed
- Inputs: policy update engine
- Outputs: recommendation scoring refresh and optional simulation rerun

9. cohort_pattern.promoted
- Purpose: validated cohort pattern promoted to memory
- Inputs: cohort learning engine
- Outputs: strategy memory update and scoring influence update

## Failure modes
- missing required fields
- stale version consumer
- subscriber without idempotency guard

## Scaling considerations
- high cardinality routing using campaign_id and tenant_id
- versioned event schema evolution

## Example code snippet
    SUBSCRIBERS = {
        'signal.updated': ['feature_handler'],
        'feature.updated': ['pattern_handler', 'recommendation_refresh_handler'],
    }

## Integration points
- app intelligence modules
- execution and outcome APIs
- strategy memory and policy engines

