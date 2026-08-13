from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    source_type: str
    source_system: str | None
    source_record_id: str | None
    source_claimed_status: str | None
    import_batch_id: str | None

    model_config = {"from_attributes": True}


class DirectoryListingDiscoveryPreviewIn(BaseModel):
    campaign_id: str


class DirectoryListingDiscoveryRunIn(DirectoryListingDiscoveryPreviewIn):
    idempotency_key: str = Field(min_length=1, max_length=160)


class AuthorityGapRefreshIn(BaseModel):
    campaign_id: str
    idempotency_key: str = Field(min_length=1, max_length=160)


class AuthorityLinkChangeRefreshIn(BaseModel):
    campaign_id: str
    idempotency_key: str = Field(min_length=1, max_length=160)


class AuthorityInventoryRefreshIn(BaseModel):
    campaign_id: str
    business_name: str = Field(min_length=2, max_length=255)
    idempotency_key: str = Field(min_length=1, max_length=160)


class AuthorityActionIn(BaseModel):
    campaign_id: str
    source_type: Literal["competitor_gap", "lost_link", "unlinked_mention"]
    source_id: str = Field(min_length=1, max_length=36)
    owner_confirmed_relevant: bool = False


class AuthorityOutreachDraftIn(AuthorityActionIn):
    pass


class AuthorityOutreachDraftUpdateIn(BaseModel):
    campaign_id: str
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_page_url: str | None = Field(default=None, max_length=2048)
    subject: str | None = Field(default=None, min_length=1, max_length=180)
    message_body: str | None = Field(default=None, min_length=1, max_length=4000)
    status: Literal["draft", "reviewed", "closed"] | None = None
    owner_confirmed_recipient: bool | None = None


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
