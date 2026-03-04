from enum import Enum


class StrategyRecommendationStatus(str, Enum):
    DRAFT = "DRAFT"
    GENERATED = "GENERATED"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    ARCHIVED = "ARCHIVED"
