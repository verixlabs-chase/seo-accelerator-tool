# Integration Flow

## Scheduling

1. A recommendation is approved.
2. `schedule_execution()` resolves governance and creates a `recommendation_executions` row.

## Planning

1. The executor turns the execution payload into deterministic structured mutations.
2. Dry runs return that mutation batch without persisting any mutation rows.

## Delivery

1. The execution engine resolves the WordPress site credentials.
2. The engine posts the mutation batch to the plugin.
3. The plugin returns per-mutation before and after state snapshots.
4. The backend persists those snapshots in `execution_mutations`.

## Rollback

1. `POST /executions/{id}/rollback` loads persisted mutation rows.
2. The backend submits rollback payloads to the plugin.
3. The execution and mutation rows are marked rolled back.
