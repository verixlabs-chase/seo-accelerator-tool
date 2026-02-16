from datetime import datetime

from pydantic import BaseModel


class CompetitorCreateIn(BaseModel):
    campaign_id: str
    domain: str
    label: str | None = None


class CompetitorOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    domain: str
    label: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

