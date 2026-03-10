from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SEOMutationOutcome(Base):
    __tablename__ = 'seo_mutation_outcomes'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    execution_id: Mapped[str] = mapped_column(String(36), ForeignKey('recommendation_executions.id', ondelete='CASCADE'), nullable=False, index=True)
    mutation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('execution_mutations.id', ondelete='SET NULL'), nullable=True, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    industry_id: Mapped[str] = mapped_column(String(120), nullable=False, default='unknown', index=True)
    page_url: Mapped[str] = mapped_column(String(500), nullable=False)
    mutation_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    mutation_parameters: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    rank_before: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rank_after: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    traffic_before: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    traffic_after: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    measured_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)
