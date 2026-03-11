# Load Testing

## Primary script

Use `backend/scripts/staging_load_simulation.py`.

This script is designed for staging validation, not production. It enforces a hostname gate and will refuse production-like hosts.

## What it exercises

- auth login
- campaign creation
- crawl scheduling
- keyword/rank creation
- entity analysis
- report scheduling
- repeated health/metrics polling

It records:

- request latencies
- failures by phase
- queue depth over time
- alert state over time
- optional process memory samples

## Safe usage

1. Run only against localhost or a staging hostname.
2. Use realistic but bounded values for crawl jobs and entity jobs.
3. Capture the output JSON for later comparison.

## Pre-run checklist

- migrations applied
- worker and beat healthy
- seed/test credentials available
- metrics endpoints reachable

## Success criteria

- failure rate within expected tolerance
- queue depth rises and then drains
- no sustained heartbeat loss
- no growing slow-query storm
- operational health returns to normal during drain phase

## Post-run review

Inspect:

- output JSON from the script
- operational health endpoint
- Prometheus queue/task metrics
- DB slow-query logs
- any failed outbox or DLQ growth
