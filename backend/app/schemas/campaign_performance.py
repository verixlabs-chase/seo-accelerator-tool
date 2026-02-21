from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class CampaignPerformanceSummaryOut(BaseModel):
    campaign_id: str
    date_from: datetime
    date_to: datetime
    clicks: float
    impressions: float
    ctr: float
    avg_position: float | None
    sessions: float
    conversions: float | None
    visibility_score: float
    traffic_growth_percent: float | None
    position_delta: float | None
    opportunity_flag: bool
    decline_flag: bool


class CampaignPerformanceTrendPointOut(BaseModel):
    period_start: date
    period_end: date
    clicks: float
    impressions: float
    ctr: float
    avg_position: float
    sessions: float
    conversions: float
    visibility_score: float


class CampaignPerformanceTrendOut(BaseModel):
    campaign_id: str
    date_from: date
    date_to: date
    interval: str
    points: list[CampaignPerformanceTrendPointOut]


class CampaignReportOverviewOut(BaseModel):
    visibility_score: float
    traffic_growth_percent: float | None
    position_delta: float | None
    opportunity_flag: bool
    decline_flag: bool


class CampaignReportPerformanceSnapshotOut(BaseModel):
    clicks: float
    impressions: float
    ctr: float
    avg_position: float | None
    sessions: float
    conversions: float | None


class CampaignReportOperationalReliabilityOut(BaseModel):
    total_calls: int
    success_rate_percent: float
    p95_latency_ms: int | None
    top_failing_provider: str | None
    top_failing_capability: str | None


class CampaignReportTrendOut(BaseModel):
    interval: str
    date_from: date
    date_to: date
    points: list[CampaignPerformanceTrendPointOut]


class CampaignReportOut(BaseModel):
    campaign_id: str
    overview: CampaignReportOverviewOut
    performance_snapshot: CampaignReportPerformanceSnapshotOut
    trend: CampaignReportTrendOut
    operational_reliability: CampaignReportOperationalReliabilityOut
