from datetime import datetime

from pydantic import BaseModel


class CampaignCreateRequest(BaseModel):
    name: str
    domain: str
    sub_account_id: str | None = None
    business_location_id: str | None = None


class CampaignSetupTransitionRequest(BaseModel):
    target_state: str


class CampaignOut(BaseModel):
    id: str
    tenant_id: str
    organization_id: str | None
    portfolio_id: str | None
    sub_account_id: str | None
    business_location_id: str | None
    name: str
    domain: str
    month_number: int
    setup_state: str
    created_at: datetime

    model_config = {"from_attributes": True}
