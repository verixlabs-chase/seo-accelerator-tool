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


class DirectoryListingOut(BaseModel):
    id: str
    campaign_id: str
    business_location_id: str
    source_key: str
    source_name: str
    external_id: str
    listing_url: str | None
    status: str
    business_name: str | None
    address_line1: str | None
    city: str | None
    region: str | None
    postal_code: str | None
    country_code: str | None
    phone: str | None
    website_url: str | None
    primary_category: str | None
    field_differences: list
    directory_importance: str
    confidence: float
    first_seen_at: datetime
    last_seen_at: datetime
    last_verified_at: datetime | None

    model_config = {"from_attributes": True}


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
