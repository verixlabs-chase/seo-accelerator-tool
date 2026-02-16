from datetime import datetime

from pydantic import BaseModel


class ReportGenerateIn(BaseModel):
    campaign_id: str
    month_number: int


class ReportDeliverIn(BaseModel):
    recipient: str


class ReportOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    month_number: int
    report_status: str
    summary_json: str
    generated_at: datetime

    model_config = {"from_attributes": True}

