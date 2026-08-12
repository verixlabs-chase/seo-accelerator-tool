from datetime import datetime

from pydantic import BaseModel


class CompetitorCreateIn(BaseModel):
    campaign_id: str
    domain: str
    label: str | None = None


class CompetitorDiscoverIn(BaseModel):
    campaign_id: str
    limit: int = 12


class CompetitorReviewIn(BaseModel):
    campaign_id: str
    competitor_id: str
    decision: str


class CompetitorOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    domain: str
    label: str | None
    discovery_source: str
    review_status: str
    overlap_count: int | None
    average_position: float | None
    estimated_traffic: float | None
    last_observed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
