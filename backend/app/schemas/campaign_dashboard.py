from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CampaignDashboardFailureItem(BaseModel):
    created_at: datetime | None
    provider_name: str
    capability: str
    outcome: str
    reason_code: str | None
    attempt_number: int
    duration_ms: int
    correlation_id: str | None


class CampaignDashboardFailurePagination(BaseModel):
    limit: int
    returned: int
    total_failures: int
    has_more: bool


class CampaignDashboardMetrics(BaseModel):
    total_calls: int
    success_count: int
    retry_count: int
    failed_count: int
    dead_letter_count: int
    success_rate_percent: float
    p95_latency_ms: int | None
    top_failing_provider: str | None
    top_failing_capability: str | None
    last_10_failures: list[CampaignDashboardFailureItem]
    last_10_failures_pagination: CampaignDashboardFailurePagination


class CampaignDashboardWindow(BaseModel):
    date_from: datetime
    date_to: datetime


class CampaignDashboardOut(BaseModel):
    campaign_id: str
    window: CampaignDashboardWindow
    metrics: CampaignDashboardMetrics
