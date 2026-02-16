from datetime import datetime

from pydantic import BaseModel


class OutreachCampaignIn(BaseModel):
    campaign_id: str
    name: str


class OutreachContactIn(BaseModel):
    campaign_id: str
    outreach_campaign_id: str
    full_name: str
    email: str


class CitationSubmissionIn(BaseModel):
    campaign_id: str
    directory_name: str


class BacklinkOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    source_url: str
    target_url: str
    quality_score: float
    status: str
    discovered_at: datetime

    model_config = {"from_attributes": True}

