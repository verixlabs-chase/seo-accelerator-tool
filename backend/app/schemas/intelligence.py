from datetime import datetime

from pydantic import BaseModel


class IntelligenceScoreOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    score_type: str
    score_value: float
    details_json: str
    captured_at: datetime

    model_config = {"from_attributes": True}


class RecommendationOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    recommendation_type: str
    rationale: str
    confidence: float
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AdvanceMonthIn(BaseModel):
    override: bool = False

