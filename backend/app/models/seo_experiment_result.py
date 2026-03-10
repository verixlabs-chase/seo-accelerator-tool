from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SEOExperimentResult(Base):
    __tablename__ = 'seo_experiment_results'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    strategy_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    variant_strategy_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    industry_id: Mapped[str] = mapped_column(String(120), nullable=False, default='unknown', index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    predicted_effect: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    actual_effect: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='proposed', index=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)
