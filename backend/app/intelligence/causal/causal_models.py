from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExperimentCompletedPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    policy_id: str
    effect_size: float
    confidence: float = Field(ge=0.0, le=1.0)
    industry: str
    sample_size: int = Field(default=1, ge=1)
    source_node: str | None = None
    target_node: str | None = None


class CausalEdgeSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')

    source_node: str
    target_node: str
    policy_id: str
    effect_size: float
    confidence: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=1)
    industry: str


class CausalPolicyPreference(BaseModel):
    model_config = ConfigDict(extra='forbid')

    policy_id: str
    effect_size: float
    confidence: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=1)
    industry: str
