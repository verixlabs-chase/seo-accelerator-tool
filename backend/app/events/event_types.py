from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    SIGNAL_UPDATED = 'signal.updated'
    FEATURE_UPDATED = 'feature.updated'
    PATTERN_DISCOVERED = 'pattern.discovered'
    RECOMMENDATION_GENERATED = 'recommendation.generated'
    SIMULATION_COMPLETED = 'simulation.completed'
    EXECUTION_SCHEDULED = 'execution.scheduled'
    EXECUTION_STARTED = 'execution.started'
    EXECUTION_COMPLETED = 'execution.completed'
    OUTCOME_RECORDED = 'outcome.recorded'
    POLICY_UPDATED = 'policy.updated'
    CAMPAIGN_PROCESSING_STARTED = 'campaign.processing.started'
    CAMPAIGN_PROCESSING_COMPLETED = 'campaign.processing.completed'
