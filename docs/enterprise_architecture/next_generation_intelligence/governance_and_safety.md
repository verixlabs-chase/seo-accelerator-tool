# Governance and Safety

## Guardrail framework
- Execution risk scoring before dispatch.
- Policy-level hard limits by action type and cohort.
- Confidence thresholds for autonomous vs assisted execution.

## Safety controls
- Simulation confidence gate for high-impact changes.
- Circuit breakers for abnormal negative outcome spikes.
- Rate-limits per campaign, tenant, and strategy class.

## Compliance and auditability
- Deterministic decision logs for every recommendation.
- Evidence lineage for graph/rule-driven decisions.
- Version tracking for models, rules, and policies.

## Incident response
- Automated rollback plans for reversible actions.
- Freeze mode for affected segments during incident.
- Replay and root-cause workflows using event history.
