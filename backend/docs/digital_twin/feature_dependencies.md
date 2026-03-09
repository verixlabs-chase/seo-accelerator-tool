# Feature Dependencies

## System definition
Defines required signal and feature dependencies for deterministic digital twin simulation.

## Why this component exists
Simulation reliability depends on explicit, versioned feature contracts.

## What problem it solves
- Prevents missing-feature runtime failures.
- Enforces deterministic defaults.
- Clarifies data ownership and lineage.

## How it integrates with the intelligence engine
Dependencies are satisfied by the existing signal assembler and feature store.

## Dependency matrix
| Feature | Source | Default | Used by |
|---|---|---|---|
| technical_issue_density | technical issues and crawl page counts | 0.0 | rank and risk prediction |
| internal_link_ratio | no_internal_links issue rate | 1.0 | internal link strategies |
| ranking_velocity | momentum slope | 0.0 | rank change prediction |
| content_growth_rate | content and temporal snapshots | 0.0 | content strategy simulation |
| local_health | local health snapshot | 0.5 | GBP and local strategy prediction |
| ctr | campaign KPI metrics | 0.0 | traffic prediction |

## Inputs and outputs
- Input: signal payloads plus temporal snapshots.
- Output: stable feature vector used by simulator.

## Failure modes
- Inconsistent units across features.
- Null values without defaults.
- Feature timestamp outside simulation window.

## Example usage
~~~python
required_defaults = {
    technical_issue_density: 0.0,
    internal_link_ratio: 1.0,
    ranking_velocity: 0.0,
    content_growth_rate: 0.0,
}
for key, default in required_defaults.items():
    features.setdefault(key, default)
~~~

## Future extensibility
- Add feature metadata registry with TTL, owner, and quality score.
