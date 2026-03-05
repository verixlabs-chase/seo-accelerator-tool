from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OnboardingStartRequest(BaseModel):
    tenant_name: str
    organization_name: str | None = None
    campaign_name: str
    campaign_domain: str
    sub_account_id: str | None = None
    provider_name: str = "google"
    provider_auth_mode: str = "api_key"
    provider_credentials: dict[str, Any] = Field(default_factory=dict)
    crawl_type: str = "deep"
    crawl_seed_url: str
    report_month_number: int = 1
    automation_override: bool = False


class OnboardingSessionOut(BaseModel):
    id: str
    tenant_id: str | None
    organization_id: str | None
    campaign_id: str | None
    status: str
    current_step: str
    step_payload: dict[str, Any]
    error_state: dict[str, Any] | None
    retry_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
