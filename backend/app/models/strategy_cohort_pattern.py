import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StrategyCohortPattern(Base):
    __tablename__ = 'strategy_cohort_patterns'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pattern_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    cohort_definition: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    pattern_strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    support_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)
