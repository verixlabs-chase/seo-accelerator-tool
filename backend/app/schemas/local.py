from datetime import datetime

from pydantic import BaseModel


class LocalProfileIn(BaseModel):
    campaign_id: str
    profile_name: str
    provider: str = "gbp"


class LocalProfileOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    provider: str
    profile_name: str
    map_pack_position: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

