from datetime import datetime

from pydantic import BaseModel


class CrawlScheduleRequest(BaseModel):
    campaign_id: str
    crawl_type: str = "deep"
    seed_url: str


class CrawlRunOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    crawl_type: str
    status: str
    seed_url: str
    pages_discovered: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class TechnicalIssueOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    crawl_run_id: str
    page_id: str | None
    issue_code: str
    severity: str
    details_json: str
    detected_at: datetime

    model_config = {"from_attributes": True}


class CrawlRunProgressOut(BaseModel):
    crawl_run_id: str
    campaign_id: str
    run_status: str
    pages_discovered: int
    frontier_total: int
    frontier_counts: dict[str, int]
