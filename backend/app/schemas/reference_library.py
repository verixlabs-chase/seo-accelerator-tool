from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ReferenceLibraryValidateIn(BaseModel):
    version: str
    artifacts: dict[str, Any] | None = None
    strict_mode: bool = True


class ReferenceLibraryActivateIn(BaseModel):
    version: str
    reason: str | None = None


class ReferenceLibraryVersionOut(BaseModel):
    version: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReferenceLibraryValidationOut(BaseModel):
    validation_run_id: str
    status: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReferenceLibraryActivationOut(BaseModel):
    activation_id: str
    version: str
    status: str


class ReferenceLibraryActiveOut(BaseModel):
    version: str
    activated_at: datetime
    activated_by: str | None = None
    artifact_types: list[str] = Field(default_factory=list)


class CoreWebVitalsEvaluateIn(BaseModel):
    measurements: dict[str, float | int | str | None]
    form_factor: str = "ALL"
    collection_period_days: int = Field(default=28, ge=1, le=366)
    measured_at: datetime | None = None
    source: str = "crux"


class CruxStandardsCheckIn(BaseModel):
    origin: str | None = None


class StandardsSourceCheckIn(BaseModel):
    source_id: str = Field(min_length=1, max_length=120)


class StandardsChangeReviewIn(BaseModel):
    disposition: Literal[
        "requires_contract_update",
        "no_product_impact",
        "editorial_only",
        "reopen",
    ]
    note: str | None = Field(default=None, max_length=4000)


class MetricContractCandidateCreateIn(BaseModel):
    standards_change_candidate_id: str = Field(min_length=1, max_length=36)
    contract_id: str = Field(min_length=1, max_length=180)
    candidate_version: str = Field(min_length=1, max_length=40)
    changes: dict[str, Any]
    effective_at: datetime | None = None


class StandardsReplayEvidenceIn(BaseModel):
    before_value: float | None = None
    after_value: float | None = None
    before_scope_key: str | None = Field(default=None, max_length=64)
    after_scope_key: str | None = Field(default=None, max_length=64)

    model_config = {"extra": "forbid"}


class MetricContractReplayIn(BaseModel):
    sample_type: Literal["fixed_fixture", "approved_evidence", "combined"] = "fixed_fixture"
    evidence_samples: list[StandardsReplayEvidenceIn] = Field(default_factory=list, max_length=200)
    approval_reference: str | None = Field(default=None, max_length=500)


class LexiconReplayEvidenceIn(BaseModel):
    metric_id: str = Field(min_length=1, max_length=180)
    value: float | None = None

    model_config = {"extra": "forbid"}


class LexiconReplayIn(BaseModel):
    base_version: str | None = Field(default=None, max_length=40)
    standards_change_candidate_id: str | None = Field(default=None, max_length=36)
    sample_type: Literal["fixed_fixture", "approved_evidence", "combined"] = "fixed_fixture"
    evidence_samples: list[LexiconReplayEvidenceIn] = Field(default_factory=list, max_length=200)
    approval_reference: str | None = Field(default=None, max_length=500)


class StandardsPlanIn(BaseModel):
    summary: str = Field(min_length=1, max_length=1000)
    steps: list[str] = Field(min_length=1, max_length=20)
    monitoring_window_hours: int = Field(default=24, ge=1, le=720)


class StandardsDecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]
    rationale: str = Field(min_length=1, max_length=4000)
    rollout_plan: StandardsPlanIn | None = None
    rollback_plan: StandardsPlanIn | None = None
    acknowledges_new_baseline: bool = False


class StandardsRolloutCreateIn(BaseModel):
    rollout_mode: Literal["immediate", "scheduled"] = "immediate"
    scheduled_for: datetime | None = None


class StandardsRollbackIn(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)


class PerformanceDriftCheckIn(BaseModel):
    metrics: list[Literal["clicks", "impressions", "avg_position"]] = Field(
        default_factory=lambda: ["clicks", "impressions", "avg_position"],
        min_length=1,
        max_length=3,
    )
    period_days: int = Field(default=14, ge=7, le=90)
    as_of: date | None = None
    minimum_organizations: int = Field(default=5, ge=5, le=100)


class PerformanceDriftReviewIn(BaseModel):
    status: Literal["investigating", "dismissed", "resolved"]
    note: str = Field(min_length=1, max_length=4000)


class AIDecisionContextIn(BaseModel):
    facts: dict[str, Any] = Field(default_factory=dict)
    deterministic_assessments: list[dict[str, Any]] = Field(default_factory=list)
    diagnostic_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)
