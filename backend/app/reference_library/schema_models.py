from typing import Literal

from pydantic import BaseModel, Field


class ArtifactMeta(BaseModel):
    purpose: str
    version: str
    generated_at: str


class MetricThresholds(BaseModel):
    good: float
    needs_improvement: float
    units: str


class MetricDefinition(BaseModel):
    metric_key: str
    thresholds: MetricThresholds
    recommendations: list[str] = Field(default_factory=list)


class MetricsArtifact(BaseModel):
    meta: ArtifactMeta = Field(alias="_meta")
    metrics: list[MetricDefinition] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class RecommendationDefinition(BaseModel):
    rec_key: str
    impact: Literal["low", "medium", "high"]
    effort: Literal["low", "medium", "high"]
    risk_tier: int = Field(ge=0, le=4)


class RecommendationsArtifact(BaseModel):
    meta: ArtifactMeta = Field(alias="_meta")
    recommendations: list[RecommendationDefinition] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
