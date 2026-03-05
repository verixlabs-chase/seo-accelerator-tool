# Simulation Queue Design

## System definition
Simulation queue design defines deterministic scheduling of Digital Twin simulations based on intelligence events.

## Purpose
Run predictive simulation only when campaign state changes can alter recommendation quality.

## Inputs
- signal.updated events for high impact signals
- feature.updated events
- recommendation.generated events
- policy.updated events

## Outputs
- queued simulation jobs
- simulation completion events
- deterministic strategy score artifacts

## Data models
- SimulationJob with id, campaign_id, trigger_event, snapshot_version, status, queued_at
- SimulationResult with job_id, strategy_id, predicted_rank_delta, predicted_traffic_delta, confidence

## Failure modes
- duplicate jobs
- stale snapshot version
- queue starvation under burst load

## Scaling considerations
- per campaign concurrency of one
- priority tiers for triggers
- dedupe key using campaign_id, snapshot_version, trigger_event

## Example code snippet
    def enqueue_simulation_job(campaign_id, trigger_event, snapshot_version):
        dedupe_key = f'{campaign_id}:{snapshot_version}:{trigger_event}'
        if pending_job_exists(dedupe_key):
            return
        create_simulation_job(campaign_id, trigger_event, snapshot_version, dedupe_key)

## Integration points
- digital twin strategy simulation engine
- strategy optimizer
- recommendation generation stage

