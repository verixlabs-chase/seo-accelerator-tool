from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


TruthState = Literal["observed", "partial", "not_measured", "unavailable"]
EvidenceState = Literal[
    "observed", "partial", "not_observed", "not_measured", "unavailable"
]


class AIVisibilityEngineOut(BaseModel):
    id: str
    code: str
    name: str
    version: str
    availability: Literal["available"]
    supported_geographies: list[str]
    supported_languages: list[str]
    supported_devices: list[str]
    limitations: list[str]


class AIVisibilityEngineListOut(BaseModel):
    truth_state: TruthState
    items: list[AIVisibilityEngineOut]
    approved_count: int
    unavailable_reason: str | None
    limitations: list[str]


class AIVisibilityQuestionOut(BaseModel):
    id: str
    text: str
    service_id: str
    service_name: str
    service_area_id: str
    service_area_name: str


class AIVisibilityQuestionSetOut(BaseModel):
    id: str
    campaign_id: str
    business_location_id: str
    version: int
    generator_version: str
    question_count: int
    questions: list[AIVisibilityQuestionOut]
    context_hash: str
    question_set_hash: str
    status: Literal["frozen"]
    created_at: datetime


class AIVisibilityNextActionOut(BaseModel):
    code: str
    label: str
    detail: str
    href: str


class AIVisibilityQuestionSetEnvelopeOut(BaseModel):
    created: bool
    question_set: AIVisibilityQuestionSetOut | None
    current_context: bool
    collection_state: Literal["unavailable"]
    next_action: AIVisibilityNextActionOut
    limitations: list[str]


class AIVisibilityTruthOut(BaseModel):
    state: TruthState
    label: str
    detail: str
    last_observed_at: datetime | None
    comparison_ready: bool


class AIVisibilitySetupOut(BaseModel):
    ready: bool
    confirmed_services: int
    confirmed_service_areas: int
    missing: list[str]
    question_set_ready: bool


class AIVisibilityEvidenceSummaryOut(BaseModel):
    checked: int
    mentioned: int
    recommended: int
    cited: int
    linked: int
    unavailable: int
    sample_size: int
    coverage: dict[str, dict[str, int]]


class AIVisibilityEnginesSummaryOut(BaseModel):
    approved_count: int
    items: list[AIVisibilityEngineOut]
    unavailable_reason: str | None


class AIVisibilityQuestionsSummaryOut(BaseModel):
    current: AIVisibilityQuestionSetOut | None
    count: int
    frozen: bool
    current_context: bool
    generator_version: str | None


class AIVisibilityHistoryOut(BaseModel):
    items: list
    total_runs: int
    comparable_runs: int
    status: EvidenceState


class AIVisibilityCompetitorsOut(BaseModel):
    items: list
    mentioned_count: int
    status: EvidenceState


class AIVisibilitySummaryOut(BaseModel):
    campaign_id: str
    business_location_id: str | None
    truth: AIVisibilityTruthOut
    setup: AIVisibilitySetupOut
    summary: AIVisibilityEvidenceSummaryOut
    engines: AIVisibilityEnginesSummaryOut
    questions: AIVisibilityQuestionsSummaryOut
    history: AIVisibilityHistoryOut
    competitors: AIVisibilityCompetitorsOut
    next_action: AIVisibilityNextActionOut
    limitations: list[str]


class AIVisibilityPreviewBlockerOut(BaseModel):
    code: str
    message: str
    href: str | None = None


class AIVisibilityPreviewChecksOut(BaseModel):
    business_context_ready: bool
    question_set_current: bool
    approved_engine_available: bool
    evidence_collection_ready: bool
    cost_rules_configured: bool
    usage_allowance_configured: bool


class AIVisibilityPreviewSideEffectsOut(BaseModel):
    external_request_sent: Literal[False]
    reservation_created: Literal[False]
    charge_created: Literal[False]
    run_created: Literal[False]


class AIVisibilityCollectionPreviewOut(BaseModel):
    campaign_id: str
    business_location_id: str | None
    state: Literal["unavailable"]
    ready: Literal[False]
    question_set_id: str | None
    question_count: int
    estimated_credits: None
    checks: AIVisibilityPreviewChecksOut
    blockers: list[AIVisibilityPreviewBlockerOut]
    side_effects: AIVisibilityPreviewSideEffectsOut
    limitations: list[str]
