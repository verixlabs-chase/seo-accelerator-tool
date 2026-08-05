from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SearchValueScopeOut(BaseModel):
    business_location_id: str | None = None
    location_name: str | None = None
    language_code: str
    device: str


class SearchValueResearchOut(BaseModel):
    run_id: str | None = None
    saved_at: str | None = None
    age_days: int | None = None
    freshness: str
    source: str
    new_paid_check_required: bool


class SearchValueEstimateOut(BaseModel):
    status: str
    central: str | None = None
    lower: str | None = None
    upper: str | None = None
    possible_central: str | None = None
    possible_lower: str | None = None
    possible_upper: str | None = None
    upside: str | None = None
    change_from_previous: str | None = None
    change_percent: float | None = None


class SearchValueCoverageOut(BaseModel):
    confirmed_phrases: int
    valued_phrases: int
    percent: float
    missing_market_data: int


class SearchValueConfidenceOut(BaseModel):
    level: str
    score: int
    reasons: list[str]


class SearchValueSourceSplitOut(BaseModel):
    measured_value: str | None = None
    modeled_value: str | None = None
    measured_share_percent: float
    modeled_share_percent: float
    measured_phrase_count: int
    modeled_phrase_count: int


class SearchValueKeywordOut(BaseModel):
    id: str
    keyword: str
    position: float | None = None
    target_position: float | None = None
    search_volume: int | None = None
    clicks: float | None = None
    click_method: str
    cpc: str | None = None
    contribution: str | None = None
    contribution_lower: str | None = None
    contribution_upper: str | None = None
    possible_contribution: str | None = None
    source: str
    source_date: str
    service: str | None = None
    location: str | None = None


class SearchValueHistoryOut(BaseModel):
    run_id: str
    saved_at: str
    status: str
    central: str | None = None
    lower: str | None = None
    upper: str | None = None
    coverage_percent: float
    measured_share_percent: float
    confidence: str
    formula_version: str


class SearchValueOut(BaseModel):
    campaign_id: str
    status: str
    formula_version: str
    ctr_model_version: str
    currency: str
    scope: SearchValueScopeOut
    research: SearchValueResearchOut
    estimate: SearchValueEstimateOut
    coverage: SearchValueCoverageOut
    confidence: SearchValueConfidenceOut
    source_split: SearchValueSourceSplitOut
    comparison: dict[str, Any] | None = None
    history: list[SearchValueHistoryOut]
    keywords: list[SearchValueKeywordOut]
    input_hash: str | None = None
    explanation: str
    caveats: list[str]
