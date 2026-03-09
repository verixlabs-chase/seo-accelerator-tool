from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IndustryIntelligenceModel(Base):
    __tablename__ = 'industry_intelligence_models'

    industry_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    industry_name: Mapped[str] = mapped_column(String(255), nullable=False)
    pattern_distribution: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False, default=dict)
    strategy_success_rates: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False, default=dict)
    avg_rank_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_traffic_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    support_state: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
