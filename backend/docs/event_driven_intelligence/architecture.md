# Event Driven Architecture

## System definition
The architecture is a deterministic event sourced control plane around existing intelligence components.

## Purpose
Provide reliable and auditable transitions from raw campaign changes to recommendations, simulations, executions, outcomes, and policy learning.

## Component map
- Event bus
- Transition router
- Feature update pipeline
- Pattern and cohort learning pipeline
- Recommendation and simulation pipeline
- Execution and outcome pipeline
- Policy update pipeline
- Monitoring and governance pipeline

## Inputs
- EventEnvelope messages from core platform services

## Outputs
- stage specific tasks
- persisted transition states
- downstream events for next stages

## Data models
- EventEnvelope with event_id, event_type, campaign_id, tenant_id, occurred_at, idempotency_key, payload
- TransitionState with campaign_id, stage, status, updated_at
- HandlerAudit with event_id, handler_name, status, deterministic_hash

## Failure modes
- stage routing misconfiguration
- duplicate transition attempts
- partial stage completion

## Scaling considerations
- queue by stage and priority
- autoscale worker pools independently
- replay from checkpoints for deterministic recovery

## Example code snippet
    ROUTES = {
        'crawl.completed': ['signals.refresh', 'features.recompute', 'patterns.detect'],
        'outcome.recorded': ['policy.update', 'metrics.snapshot'],
    }

## Integration points
- app tasks intelligence tasks
- app intelligence intelligence orchestrator
- app services strategy engine

