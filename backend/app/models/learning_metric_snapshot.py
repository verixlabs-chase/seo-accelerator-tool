import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LearningMetricSnapshot(Base):
    __tablename__ = 'learning_metrics'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)
    mutation_success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    experiment_win_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    causal_confidence_mean: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    policy_improvement_velocity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mutation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    experiment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
