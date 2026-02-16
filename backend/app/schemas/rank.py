from datetime import datetime

from pydantic import BaseModel


class RankKeywordIn(BaseModel):
    campaign_id: str
    cluster_name: str
    keyword: str
    location_code: str = "US"


class RankScheduleIn(BaseModel):
    campaign_id: str
    location_code: str = "US"


class RankingSnapshotOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    keyword_id: str
    position: int
    confidence: float
    captured_at: datetime
    month_partition: str

    model_config = {"from_attributes": True}

