# Event Architecture

## Event role
Events trigger extraction, feature recomputation, outcome tracking, and learning refresh jobs.

## Core event types
- crawl.completed
- rank.snapshot.created
- local.health.updated
- report.generated
- intelligence.score.computed
- recommendation.generated
- recommendation.transitioned
- automation.action_executed
- automation.evaluation_completed
- campaign.milestone_reached

## Event flow

Event producers
   |
   v
Event bus and audit envelope
   |
   +--> signal extractor trigger
   +--> feature refresh trigger
   +--> outcome tracker trigger
   +--> learning cycle scheduler

## Event payload baseline
- event_id
- tenant_id
- campaign_id
- event_type
- occurred_at
- correlation_id
- payload
- schema_version

## Example payload

    {
      event_type: automation.action_executed,
      tenant_id: t_001,
      campaign_id: cmp_001,
      occurred_at: 2026-03-05T03:10:00Z,
      correlation_id: corr_99,
      payload: {
        recommendation_id: rec_001,
        action_id: act_100,
        status: completed
      },
      schema_version: event_schema_v1
    }

## Existing event hooks
- app/events/emitter.py for event envelopes
- app/observability/events.py for automation observability events
- app/tasks/tasks.py for async task triggers
