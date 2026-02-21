from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_name: str
    signal_value: float | bool | None
    threshold_reference: str
    comparator: str
    comparative_value: float | bool | None = None
    window_reference: str


class DiagnosticResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    confidence: float = Field(ge=0, le=1)
    signal_magnitude: float = Field(ge=0, le=1)
    evidence: list[Evidence]


class StrategyWindow(BaseModel):
    date_from: datetime
    date_to: datetime


class StrategyRecommendationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    priority_score: float
    diagnosis: str
    root_cause: str
    recommended_actions: list[str]
    expected_outcome: str
    authoritative_sources: list[str]
    confidence: float
    impact_level: str
    evidence: list[Evidence]


class StrategicScoreOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_score: float = Field(ge=0, le=100)
    technical_health_score: float = Field(ge=0, le=100)
    competitive_pressure_score: float | None = Field(default=None, ge=0, le=100)
    local_authority_score: float = Field(ge=0, le=100)
    risk_index: float = Field(ge=0, le=100)
    opportunity_index: float = Field(ge=0, le=100)


class ExecutiveSummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_issue_category: str
    top_priority_scenario: str | None
    dominant_score_dimension: str
    strategic_theme: str
    recommended_focus_area: str
    summary_confidence: float = Field(ge=0, le=1)


class CampaignStrategyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str
    window: StrategyWindow
    detected_scenarios: list[str]
    recommendations: list[StrategyRecommendationOut]
    strategic_scores: StrategicScoreOut | None = None
    executive_summary: ExecutiveSummaryOut | None = None
    meta: dict
