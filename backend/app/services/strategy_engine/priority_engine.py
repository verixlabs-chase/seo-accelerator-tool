from __future__ import annotations

from pydantic import BaseModel, Field


class PriorityInput(BaseModel):
    scenario_id: str
    impact_weight: float = Field(ge=0, le=1)
    signal_magnitude: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)


class PriorityResult(BaseModel):
    scenario_id: str
    priority_score: float
    impact_weight: float


def calculate_priority_score(impact_weight: float, signal_magnitude: float, confidence: float) -> float:
    return impact_weight * signal_magnitude * confidence


def rank_priorities(inputs: list[PriorityInput]) -> list[PriorityResult]:
    scored = [
        PriorityResult(
            scenario_id=item.scenario_id,
            priority_score=calculate_priority_score(item.impact_weight, item.signal_magnitude, item.confidence),
            impact_weight=item.impact_weight,
        )
        for item in inputs
    ]
    return sorted(
        scored,
        key=lambda item: (-item.priority_score, -item.impact_weight, item.scenario_id),
    )

