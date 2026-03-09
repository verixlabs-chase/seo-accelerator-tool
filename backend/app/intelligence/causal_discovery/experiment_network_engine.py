from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.digital_twin.strategy_simulation_engine import simulate_strategy
from app.intelligence.digital_twin.twin_state_model import DigitalTwinState

PSEUDOCODE = """
1. Take discovered strategy hypotheses and a target campaign cohort.
2. Build digital twin state for each candidate campaign.
3. Simulate the hypothesis mutation pattern before any live test is created.
4. Keep only candidates above expected value and confidence thresholds.
5. Return experiment plans for the existing strategy evolution experiment engine.
"""


@dataclass(slots=True)
class ExperimentCandidate:
    campaign_id: str
    strategy_id: str
    expected_value: float
    confidence: float
    mutation_pattern: dict[str, object]


def plan_experiment_candidates(
    db: Session,
    *,
    hypotheses: list[dict[str, Any]],
    campaign_ids: list[str],
    minimum_expected_value: float = 0.1,
    minimum_confidence: float = 0.6,
) -> list[dict[str, Any]]:
    planned: list[ExperimentCandidate] = []
    for campaign_id in campaign_ids:
        twin_state = DigitalTwinState.from_campaign_data(db, campaign_id)
        for hypothesis in hypotheses:
            strategy_actions = _mutation_pattern_to_actions(dict(hypothesis.get('mutation_pattern') or {}))
            simulation = simulate_strategy(
                twin_state,
                strategy_actions,
                db=None,
                strategy_id=str(hypothesis.get('strategy_id') or ''),
            )
            expected_value = float(simulation.get('expected_value', 0.0) or 0.0)
            confidence = float(simulation.get('confidence', 0.0) or 0.0)
            if expected_value < minimum_expected_value or confidence < minimum_confidence:
                continue
            planned.append(
                ExperimentCandidate(
                    campaign_id=campaign_id,
                    strategy_id=str(hypothesis.get('strategy_id') or ''),
                    expected_value=round(expected_value, 6),
                    confidence=round(confidence, 6),
                    mutation_pattern=dict(hypothesis.get('mutation_pattern') or {}),
                )
            )
    return [asdict(item) for item in planned]


def _mutation_pattern_to_actions(pattern: dict[str, object]) -> list[dict[str, object]]:
    mutation_types = pattern.get('mutation_types')
    if isinstance(mutation_types, list) and 'insert_internal_link' in mutation_types:
        return [{
            'type': 'internal_link',
            'count': int(pattern.get('minimum_links_per_page', 1) or 1),
            'cohort_pattern_strength': float(pattern.get('confidence_score', 0.7) or 0.7),
        }]
    if isinstance(mutation_types, list) and 'add_schema_markup' in mutation_types:
        return [{'type': 'fix_technical_issues', 'count': 1, 'cohort_pattern_strength': 0.7}]
    return [{'type': 'publish_content', 'pages': 1, 'cohort_pattern_strength': 0.6}]
