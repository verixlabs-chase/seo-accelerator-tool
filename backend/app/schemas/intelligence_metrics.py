from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class IntelligenceMetricsSnapshotOut(BaseModel):
    id: str
    campaign_id: str
    metric_date: date
    signals_processed: int
    features_computed: int
    patterns_detected: int
    recommendations_generated: int
    executions_run: int
    positive_outcomes: int
    negative_outcomes: int
    policy_updates_applied: int
    created_at: datetime

    model_config = {'from_attributes': True}


class CampaignIntelligenceMetricsOut(BaseModel):
    snapshot: IntelligenceMetricsSnapshotOut
    recommendation_success_rate: float
    execution_success_rate: float
    pattern_discovery_rate: float
    learning_velocity: float
    campaign_improvement_trend: float


class SystemIntelligenceMetricsOut(BaseModel):
    campaigns_tracked: int
    signals_processed: int
    features_computed: int
    patterns_detected: int
    recommendations_generated: int
    executions_run: int
    positive_outcomes: int
    negative_outcomes: int
    policy_updates_applied: int
    recommendation_success_rate: float
    execution_success_rate: float
    pattern_discovery_rate: float
    learning_velocity: float
    average_outcome_delta: float


class IntelligenceTrendsOut(BaseModel):
    campaign_id: str | None = None
    window_days: int
    success_rate_over_time: list[dict[str, object]]
    pattern_growth_rate: float
    policy_weight_changes: dict[str, float | int]
    average_outcome_delta: float
    pattern_discovery_rate: float
    learning_velocity: float
    campaign_improvement_trend: float
