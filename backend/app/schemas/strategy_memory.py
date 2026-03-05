from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class StrategyMemoryPatternOut(BaseModel):
    id: str
    pattern_name: str
    feature_name: str
    pattern_description: str
    support_count: int
    avg_outcome_delta: float
    confidence_score: float
    created_at: datetime
    updated_at: datetime

    model_config = {'from_attributes': True}
