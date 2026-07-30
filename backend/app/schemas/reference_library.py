from datetime import datetime
from typing import Any

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


class AIDecisionContextIn(BaseModel):
    facts: dict[str, Any] = Field(default_factory=dict)
    deterministic_assessments: list[dict[str, Any]] = Field(default_factory=list)
    diagnostic_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)
