from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PolicyPayload(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    policy_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    priority_weight: float = Field(ge=0.0, le=1.0)
    evidence: list[Any] = Field(default_factory=list)


class PolicyBundle(BaseModel):
    model_config = ConfigDict(extra='forbid')

    policies: list[PolicyPayload]
