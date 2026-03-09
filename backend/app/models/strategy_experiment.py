from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StrategyExperiment(Base):
    __tablename__ = 'strategy_experiments'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    variant_strategy_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('campaigns.id', ondelete='SET NULL'), nullable=True, index=True)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    mutation_payload: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    predicted_rank_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    predicted_traffic_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    expected_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='proposed', index=True)
    result_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
