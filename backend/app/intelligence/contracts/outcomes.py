from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OutcomePayload(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    recommendation_type: str = Field(min_length=1)
    outcome_type: str = Field(min_length=1)
    delta: float | None = None
    evidence: list[Any] = Field(default_factory=list)


class OutcomeBundle(BaseModel):
    model_config = ConfigDict(extra='forbid')

    outcomes: list[OutcomePayload]
