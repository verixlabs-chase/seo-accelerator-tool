from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrongPolicyCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    policy_id: str
    industry: str
    effect_size: float
    confidence: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=1)


class PolicyMutationCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    parent_policy: str
    new_policy: str
    mutation_type: str
    industry: str
    expected_effect: float
    confidence: float = Field(ge=0.0, le=1.0)


class RegisteredPolicyEntry(BaseModel):
    model_config = ConfigDict(extra='forbid')

    policy_id: str
    parent_policy: str
    mutation_type: str
    industry: str
    status: str


class StrategyEvolutionResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    candidates: list[StrongPolicyCandidate]
    mutations: list[PolicyMutationCandidate]
    registered_policies: list[RegisteredPolicyEntry]
    experiments_triggered: list[str]
