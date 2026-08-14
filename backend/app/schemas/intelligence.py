from datetime import datetime
import json

from typing import Literal

from pydantic import BaseModel, Field, computed_field


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


class AskIntelligenceQuestionIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    retry_failed: bool = False


class GenerateIntelligenceDraftIn(BaseModel):
    action_id: str = Field(min_length=1, max_length=160)
    draft_type: Literal[
        "search_result",
        "review_request",
        "review_response",
        "page_outline",
    ]
    refresh: bool = False
    retry_failed: bool = False


class ActionPlanStepUpdateIn(BaseModel):
    status: Literal["not_started", "in_progress", "done", "skipped", "blocked"]
    blocker_reason: str | None = Field(default=None, max_length=1000)
    evidence: list[str] | None = Field(default=None, max_length=20)


class OutcomeLearningReviewIn(BaseModel):
    decision: Literal["pending", "included", "excluded"]
    confounder_codes: list[
        Literal[
            "other_website_changes",
            "google_or_search_change",
            "seasonal_demand",
            "tracking_change",
            "other_marketing",
            "website_outage",
            "other",
        ]
    ] = Field(default_factory=list, max_length=7)
    note: str | None = Field(default=None, max_length=1000)


class GovernedExperimentPlanCreateIn(BaseModel):
    action_id: str = Field(min_length=1, max_length=160)
    metric_id: str = Field(min_length=1, max_length=160)
    measurement_contract_version: str = Field(min_length=1, max_length=80)
    hypothesis: str = Field(min_length=10, max_length=1000)
    design_type: Literal[
        "content_split",
        "staggered_rollout",
        "holdout_comparison",
    ]
    minimum_sample_size: int = Field(default=10, ge=5, le=1000)
    observation_window_days: int = Field(default=28, ge=7, le=180)
    guardrail_metric_ids: list[str] = Field(default_factory=list, max_length=10)
    rollback_steps: list[str] = Field(min_length=1, max_length=10)


class GovernedExperimentPlanReviewIn(BaseModel):
    decision: Literal["approved", "rejected", "cancelled"]
    note: str | None = Field(default=None, max_length=1000)


class GovernedExperimentProtocolAuthorizeIn(BaseModel):
    reviewed_frozen_plan: bool = False
    rollback_ready: bool = False
    understands_no_change_is_made: bool = False
    note: str | None = Field(default=None, max_length=1000)


class GovernedExperimentProtocolStartIn(BaseModel):
    evidence_references: list[str] = Field(min_length=1, max_length=20)
    change_applied_at: datetime | None = None


class GovernedExperimentProtocolStopIn(BaseModel):
    reason_code: Literal[
        "safety_issue",
        "primary_metric_regression",
        "protected_metric_regression",
        "data_quality_loss",
        "allowance_exhausted",
        "owner_request",
    ]
    note: str | None = Field(default=None, max_length=1000)


class GovernedExperimentProtocolRollbackIn(BaseModel):
    rollback_steps_confirmed: bool = False
    evidence_references: list[str] = Field(min_length=1, max_length=20)


class GovernedPolicyCandidateReviewIn(BaseModel):
    decision: Literal[
        "approved_for_future_activation",
        "rejected",
        "cancelled",
    ]
    replay_id: str | None = Field(default=None, max_length=36)
    reviewed_rule_comparison: bool = False
    understands_not_active: bool = False
    understands_no_causal_proof: bool = False
    note: str | None = Field(default=None, max_length=1000)
