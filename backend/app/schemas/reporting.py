from datetime import datetime

from pydantic import BaseModel, field_validator


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


class ReportScheduleUpsertIn(BaseModel):
    campaign_id: str
    cadence: str
    timezone: str
    next_run_at: datetime
    enabled: bool = True

    @field_validator("cadence")
    @classmethod
    def validate_cadence(cls, value: str) -> str:
        allowed = {"daily", "weekly", "monthly"}
        if value not in allowed:
            raise ValueError("cadence must be one of: daily, weekly, monthly")
        return value


class ReportScheduleOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    cadence: str
    timezone: str
    next_run_at: datetime
    enabled: bool
    retry_count: int
    last_status: str

    model_config = {"from_attributes": True}
