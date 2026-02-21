from __future__ import annotations

import pytest

from app.services.strategy_engine.priority_engine import (
    PriorityInput,
    calculate_priority_score,
    rank_priorities,
)


def test_calculate_priority_score_is_deterministic() -> None:
    score = calculate_priority_score(0.8, 0.5, 0.9)
    assert score == pytest.approx(0.36)


def test_rank_priorities_applies_tiebreak_order() -> None:
    ranked = rank_priorities(
        [
            PriorityInput(scenario_id="b", impact_weight=0.7, signal_magnitude=0.5, confidence=1.0),  # 0.35
            PriorityInput(scenario_id="a", impact_weight=0.7, signal_magnitude=0.5, confidence=1.0),  # 0.35
            PriorityInput(scenario_id="c", impact_weight=0.6, signal_magnitude=0.4, confidence=1.0),  # 0.24
        ]
    )
    assert [item.scenario_id for item in ranked] == ["a", "b", "c"]
