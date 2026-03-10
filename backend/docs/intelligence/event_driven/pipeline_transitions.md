# Pipeline Transitions

## System definition
Pipeline transitions are deterministic stage changes driven by accepted events.

## Purpose
Move from full cycle orchestration to incremental stage transitions.

## Transition chain example
crawl.completed
-> signal.updated
-> feature.updated
-> pattern.discovered
-> recommendation.generated
-> simulation.requested
-> execution.scheduled
-> execution.completed
-> outcome.recorded
-> policy.updated

## Inputs
- incoming event envelope
- campaign transition checkpoint

## Outputs
- next stage task dispatch
- updated checkpoint state

## Data models
- TransitionRule with trigger_event, from_stage, to_stage, handler
- TransitionState with campaign_id, current_stage, status, updated_at

## Failure modes
- skipped transition from invalid rules
- duplicate transition attempts
- blocked transition due to unmet dependency

## Scaling considerations
- separate queues by stage
- high priority lane for recommendation and execution stages

## Example code snippet
    def advance_transition(state, event):
        rule = resolve_transition_rule(state.current_stage, event.event_type)
        if rule is None:
            return state
        return apply_transition_rule(state, rule)

## Integration points
- intelligence orchestrator
- event bus consumers

