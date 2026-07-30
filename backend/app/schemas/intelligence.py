from datetime import datetime
import json

from pydantic import BaseModel, computed_field


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
    confidence_score: float
    evidence_json: str
    risk_tier: int
    rollback_plan_json: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}

    @computed_field(return_type=list[str])
    def evidence(self) -> list[str]:
        try:
            data = json.loads(self.evidence_json or "[]")
        except json.JSONDecodeError:
            return []
        if isinstance(data, list):
            return [str(item) for item in data]
        if isinstance(data, dict) and isinstance(data.get("evidence"), list):
            return [str(item) for item in data["evidence"]]
        return []

    @computed_field(return_type=str)
    def engine_source(self) -> str:
        if self.recommendation_type.startswith(("policy::", "transfer::")):
            return "orchestrator_v1"
        try:
            data = json.loads(self.evidence_json or "[]")
        except json.JSONDecodeError:
            data = []
        if isinstance(data, dict) and data.get("policy_id"):
            return "orchestrator_v1"
        return "heuristic_threshold_v1"

    @computed_field(return_type=dict)
    def rollback_plan(self) -> dict:
        try:
            data = json.loads(self.rollback_plan_json or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}


class AdvanceMonthIn(BaseModel):
    override: bool = False


class RecommendationTransitionIn(BaseModel):
    target_state: str


class GenerateIntelligenceBriefIn(BaseModel):
    retry_failed: bool = False
