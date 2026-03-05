# Failure Handling

## System definition
Failure handling defines deterministic retry, dead letter, and replay behavior for the event pipeline.

## Purpose
Contain faults and preserve data integrity under transient and permanent errors.

## Inputs
- handler exceptions
- payload validation errors
- broker delivery failures

## Outputs
- retries for recoverable failures
- dead letter entries for unrecoverable failures
- alert events for operator visibility

## Data models
- RetryState with event_id, handler, attempts, next_retry_at
- DeadLetterEvent with event_id, reason, payload, attempts
- ErrorAudit with event_id, error_code, message, occurred_at

## Failure modes
- transient database connectivity loss
- schema mismatch between producer and consumer
- poison messages that always fail

## Scaling considerations
- isolate failing handlers by queue
- replay by partition and time window
- bounded retries to avoid queue starvation

## Example code snippet
    def process_event(envelope):
        try:
            handle_event(envelope)
        except TransientError:
            schedule_retry(envelope)
        except Exception as exc:
            move_to_dead_letter(envelope, str(exc))

## Integration points
- event bus and subscriber framework
- observability and safety monitor

