from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EntityAnalyzeIn(BaseModel):
    campaign_id: str


class EntityRecommendationV1(BaseModel):
    recommendation_type: str
    confidence_score: float
    evidence: list[str]
    expected_impact: str
    risk_tier: int
    rollback_plan: dict[str, Any]


class EntityReportOut(BaseModel):
    id: str
    campaign_id: str
    entity_score: float
    missing_entities: list[str]
    confidence_score: float
    evidence: list[str]
    recommendations: list[EntityRecommendationV1]
    created_at: datetime
