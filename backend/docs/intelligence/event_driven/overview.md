# Event Driven Intelligence Pipeline Overview

## System definition
The event driven intelligence pipeline is a deterministic processing architecture that reacts to campaign state changes and runs only impacted intelligence stages.

## Purpose
This component defines the canonical runtime event flow. The current implementation is synchronous/in-process for intelligence events and should not be read as a durable distributed event platform yet.

## Problem solved
Batch cycles recompute unchanged data. Event driven transitions reduce compute waste, queue contention, and latency.

## Inputs
- crawl, report, automation, recommendation, and outcome state changes
- campaign metadata and governance settings
- existing signal and feature snapshots

## Outputs
- updated signals and features
- new pattern and recommendation triggers
- simulation jobs
- execution and outcome learning events

## Data models
- EventEnvelope
- PipelineTransitionState
- EventProcessingCheckpoint
- SimulationJob
- RecommendationExecution
- RecommendationOutcome

## Failure modes
- duplicate event delivery
- out of order event arrival
- malformed payloads
- subscriber timeout and retry exhaustion

## Scaling considerations
- partition by tenant_id and campaign_id
- idempotent handlers per event id
- bounded retries and dead letter queue
- queue isolation for heavy stages

## Example code snippet
    def on_crawl_completed(event):
        if already_processed(event.event_id):
            return
        signals = assemble_signals(event.campaign_id)
        write_temporal_signals(event.campaign_id, signals)
        publish_event('signal.updated', {'campaign_id': event.campaign_id})

## Integration points
- app intelligence modules
- strategy engine and execution engine
- metrics aggregation and observability APIs

