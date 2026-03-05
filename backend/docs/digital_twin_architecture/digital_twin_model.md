# Digital Twin Model

## System definition
Digital Twin Model is the canonical immutable campaign state object used by simulation and optimization stages.

## Why this component exists
A unified state model avoids scattered reads and inconsistent scoring input.

## What problem it solves
- Normalizes campaign context for deterministic simulation.
- Enables state hashing and replay.
- Simplifies integration contracts.

## How it integrates with the intelligence engine
Twin state is assembled from deterministic intelligence outputs and used directly by simulation and optimizer layers.

## Data model
~~~python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class DigitalTwinState:
    campaign_id: str
    observed_at: datetime
    ranking_signals: dict[str, float]
    content_inventory: dict[str, float]
    internal_link_graph: dict[str, float]
    technical_issue_graph: dict[str, float]
    local_search_signals: dict[str, float]
    campaign_momentum_metrics: dict[str, float]
    feature_vector: dict[str, float]
    local_patterns: list[dict[str, object]]
    cohort_patterns: list[dict[str, object]]
    state_hash: str
~~~

## Inputs
- Ranking metrics and velocity
- Content count and growth metrics
- Technical issue density and crawl health
- Local health and review dynamics
- Pattern evidence from local and cohort engines

## Outputs
- Stable JSON-serializable state payload for simulation runs.

## Failure modes
- Missing campaign_id
- Non-numeric feature values
- Stale observed_at versus signal window

## Example usage
~~~python
state = build_twin_state(campaign_id, db)
assert state.state_hash
~~~

## Integration points
- [signal_assembler.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/signal_assembler.py)
- [feature_store.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/feature_store.py)
- [pattern_engine.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/pattern_engine.py)
- [cohort_pattern_engine.py](/home/verixlabs/SEO Accelerator Tool/backend/app/intelligence/cohort_pattern_engine.py)

## Future extensibility
- Add graph adjacency structures for internal link topology.
- Add per-page cluster state blocks.
