import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StrategyMemoryPattern(Base):
    __tablename__ = 'strategy_memory_patterns'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pattern_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    feature_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    pattern_description: Mapped[str] = mapped_column(String(500), nullable=False)
    support_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_outcome_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        index=True,
    )
