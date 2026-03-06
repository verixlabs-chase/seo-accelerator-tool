from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class IndustryModel:
    industry_id: str
    industry_name: str
    pattern_distribution: dict[str, float] = field(default_factory=dict)
    strategy_success_rates: dict[str, float] = field(default_factory=dict)
    avg_rank_delta: float = 0.0
    avg_traffic_delta: float = 0.0
    confidence_score: float = 0.0
    sample_size: int = 0
    last_updated: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
