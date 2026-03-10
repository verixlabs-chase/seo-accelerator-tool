import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LearningReport(Base):
    __tablename__ = 'learning_reports'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    mutation_success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    experiment_win_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    policy_improvement_velocity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    causal_confidence_mean: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    trend: Mapped[str] = mapped_column(String(32), nullable=False, default='stable')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)
