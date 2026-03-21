from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class OrganicValueBaselineRequest(BaseModel):
    monthly_seo_investment: Decimal | None = Field(default=None, ge=0)
    persist_assumptions: bool = True
    clear_monthly_seo_investment: bool = False


class OrganicValueBaselineMetricOut(BaseModel):
    amount: str | None = None
    ratio: str | None = None
    net_amount: str | None = None
    currency: str = "USD"
    status: str
    source_type: str
    label: str


class OrganicValueBaselineAssumptionOut(BaseModel):
    key: str
    label: str
    value: str | None = None
    status: str
    source_type: str
    note: str | None = None


class OrganicValueBaselineScenarioOut(BaseModel):
    key: str
    label: str
    projected_value: str
    upside_value: str
    percentage_lift: str
    target_rank_rule: str
    roi_baseline: OrganicValueBaselineMetricOut


class OrganicValueBaselineKeywordDriverOut(BaseModel):
    keyword_id: str
    keyword: str | None = None
    current_value: str | None = None
    projected_value: str | None = None
    upside_value: str | None = None
    current_rank: int | None = None
    projected_rank: int | None = None
    ctr_model_version: str | None = None


class OrganicValueBaselineConfidenceOut(BaseModel):
    level: str
    score: str
    reasons: list[str]


class OrganicValueBaselineOut(BaseModel):
    campaign_id: str
    feature: str
    currency: str
    as_of: str | None = None
    current_value: OrganicValueBaselineMetricOut
    upside_opportunity: OrganicValueBaselineMetricOut
    roi_baseline: OrganicValueBaselineMetricOut
    scenarios: list[OrganicValueBaselineScenarioOut]
    assumptions: list[OrganicValueBaselineAssumptionOut]
    confidence: OrganicValueBaselineConfidenceOut
    top_keywords_by_value: list[OrganicValueBaselineKeywordDriverOut]
    opportunity_drivers: list[OrganicValueBaselineKeywordDriverOut]
    caveats: list[str]
