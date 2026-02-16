from datetime import datetime

from pydantic import BaseModel


class CampaignCreateRequest(BaseModel):
    name: str
    domain: str


class CampaignOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    domain: str
    month_number: int
    created_at: datetime

    model_config = {"from_attributes": True}

