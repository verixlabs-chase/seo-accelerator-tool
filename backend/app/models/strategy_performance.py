from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StrategyPerformance(Base):
    __tablename__ = 'strategy_performance'

    strategy_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    recommendation_type: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    policy_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    lifecycle_stage: Mapped[str] = mapped_column(String(32), nullable=False, default='candidate', index=True)
    performance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    graph_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    industry_prior: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    promotion_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    demotion_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
