# Code Examples

## System definition
This file provides Python-style examples for implementing deterministic Digital Twin interfaces.

## Why this component exists
Concrete examples reduce ambiguity for engineers and AI coding agents.

## What problem it solves
- Establishes canonical method signatures and output contracts.

## How it integrates with the intelligence engine
Examples call existing intelligence modules for state assembly and feedback integration.

## DigitalTwinState class
~~~python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class DigitalTwinState:
    campaign_id: str
    observed_at: datetime
    features: dict[str, float]
    patterns: list[dict[str, object]]
    cohort_patterns: list[dict[str, object]]
~~~

## assemble twin state
~~~python
from app.intelligence.signal_assembler import assemble_signals
from app.intelligence.feature_store import compute_features
from app.intelligence.pattern_engine import discover_patterns_for_campaign, discover_cohort_patterns


def build_twin_state(campaign_id: str, db):
    signals = assemble_signals(campaign_id, db=db)
    features = compute_features(campaign_id, db=db, persist=False)
    patterns = discover_patterns_for_campaign(campaign_id, db=db, persist_features=False)
    cohort_patterns = discover_cohort_patterns(db, campaign_id=campaign_id, features=features)
    return {
        campaign_id: campaign_id,
        observed_at: 2026-03-05T00:00:00Z,
        signals: signals,
        features: features,
        patterns: patterns,
        cohort_patterns: cohort_patterns,
    }
~~~

## simulate strategy
~~~python
def predict_rank_change(features: dict[str, float], execution_type: str) -> float:
    base = -features.get(technical_issue_density, 0.0)
    if execution_type == improve_internal_links:
        base += 2.0 * features.get(internal_link_ratio, 0.0)
    if execution_type == create_content_brief:
        base += 1.5 * features.get(content_growth_rate, 0.0)
    base += 0.8 * features.get(ranking_velocity, 0.0)
    return base


def simulate_strategy(state: dict, execution_type: str) -> dict:
    rank_delta = predict_rank_change(state[features], execution_type)
    traffic_delta = max(0.0, rank_delta * 6.0)
    confidence = min(1.0, 0.55 + 0.05 * len(state[patterns]))
    return {
        predicted_rank_delta: round(rank_delta, 4),
        predicted_traffic_delta: round(traffic_delta, 4),
        confidence: round(confidence, 4),
    }
~~~

## optimize strategy
~~~python
def optimize_strategy(sim_results: list[dict]) -> list[dict]:
    for row in sim_results:
        row[expected_value] = row[predicted_traffic_delta] * row[confidence]
    return sorted(sim_results, key=lambda x: (-x[expected_value], x.get(execution_type, )))
~~~

## canonical output
~~~json
{
  predicted_rank_delta: 2.4,
  predicted_traffic_delta: 18.2,
  confidence: 0.71
}
~~~

## Failure modes
- Unknown execution type.
- Missing required feature keys.
- Non-numeric input values.

## Future extensibility
- Add strict pydantic schema contracts once model layer is implemented.
