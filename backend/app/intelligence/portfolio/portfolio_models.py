from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CampaignPerformanceSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')

    campaign_id: str
    ranking_velocity: float = 0.0
    content_velocity: float = 0.0
    link_velocity: float = 0.0
    review_velocity: float = 0.0
    campaign_performance_score: float = Field(ge=0.0, le=1.0)


class PolicyPerformanceSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')

    policy_id: str
    campaign_id: str
    industry: str
    success_score: float
    execution_count: int
    confidence: float = Field(ge=0.0, le=1.0)


class PolicyAllocation(BaseModel):
    model_config = ConfigDict(extra='forbid')

    policy_id: str
    campaign_id: str
    industry: str
    mode: str
    success_score: float
    confidence: float = Field(ge=0.0, le=1.0)


class PortfolioAllocationResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    campaign_id: str
    industry: str
    updated_policy_id: str
    allocations: list[PolicyAllocation]
