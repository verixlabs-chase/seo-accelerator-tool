# Diagrams

## Full intelligence pipeline diagram

signals
  -> event bus
  -> feature updates
  -> pattern detection
  -> cohort learning
  -> recommendations
  -> digital twin simulation
  -> execution
  -> outcomes
  -> policy learning

## Event flow diagram

crawl.completed
  -> signal.updated
  -> feature.updated
  -> pattern.discovered
  -> recommendation.generated
  -> simulation.requested
  -> simulation.completed
  -> execution.scheduled
  -> execution.completed
  -> outcome.recorded
  -> policy.updated

## System component diagram

[Crawl Reports Automation Sources]
                |
                v
            [Event Bus]
                |
                v
        [Transition Router]
          |            |
          v            v
 [Feature Pipeline] [Pattern Pipelines]
          |            |
          +-----+------+ 
                v
      [Recommendation Engine]
                |
                v
      [Simulation Queue and Twin]
                |
                v
         [Execution Engine]
                |
                v
          [Outcome Tracker]
                |
                v
        [Policy Update Engine]

## Queue architecture diagram

+------------------+
| Event Bus Topics |
+------------------+
         |
+--------+--------+
| Feature Queue   |
| Pattern Queue   |
| Recommendation  |
+--------+--------+
         |
  +------+------+
  | Simulation  |
  +------+------+
         |
  +------+------+
  | Execution   |
  +------+------+
         |
  +------+------+
  | Outcome and |
  | Policy Q    |
  +-------------+

## Purpose
Provide quick visual references for architecture review and onboarding.

## Inputs
- event contracts
- transition definitions

## Outputs
- canonical ASCII architecture references

## Data models
- EventEnvelope
- SimulationJob
- RecommendationExecution

## Failure modes
- documentation drift from implementation

## Scaling considerations
- queue isolation and stage parallelism are explicit in diagrams

## Example code snippet
    queue_name = route_event_to_queue(event_type)
    broker_publish(queue_name, envelope)

## Integration points
- architecture and event catalog documents
- simulation and execution flow documents

