from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class KnowledgePolicyPreference(BaseModel):
    model_config = ConfigDict(extra='forbid')

    policy_id: str
    effect_size: float
    confidence: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=1)
    industry: str
