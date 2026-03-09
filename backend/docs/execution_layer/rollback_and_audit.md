# Rollback And Audit

## Persisted Audit Trail

Each applied mutation is stored in `execution_mutations` with:

- `execution_id`
- `recommendation_id`
- `campaign_id`
- `provider_name`
- `mutation_type`
- `target_url`
- `mutation_payload`
- `before_state`
- `after_state`
- `rollback_payload`
- `status`
- `applied_at`
- `rolled_back_at`

Execution-level rollback state is also stored on `recommendation_executions.rolled_back_at`.

## Rollback API

`POST /api/v1/executions/{id}/rollback`

Rollback is allowed only when:

- the execution exists in the tenant scope
- the execution is `completed` or already `rolled_back`
- persisted mutation rows exist

The backend replays rollback payloads through the WordPress transport and marks both the execution and mutation rows as rolled back.
