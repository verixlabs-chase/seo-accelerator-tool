from datetime import datetime

from pydantic import BaseModel


class ContentAssetCreateIn(BaseModel):
    campaign_id: str
    cluster_name: str
    title: str
    planned_month: int = 1


class ContentAssetUpdateIn(BaseModel):
    status: str | None = None
    title: str | None = None
    target_url: str | None = None


class ContentAssetOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    cluster_name: str
    title: str
    status: str
    target_url: str | None
    planned_month: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

