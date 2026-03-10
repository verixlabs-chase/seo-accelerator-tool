from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExperimentResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    experiment_id: str
    policy_id: str
    industry: str
    treatment_success_rate: float
    control_success_rate: float
    effect_size: float
    confidence: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=0)


class ExperimentAssignmentResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    experiment_id: str
    campaign_id: str
    cohort: str
    policy_id: str
    assigned_policy_id: str
