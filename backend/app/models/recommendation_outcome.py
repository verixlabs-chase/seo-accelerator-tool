import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RecommendationOutcome(Base):
    __tablename__ = 'recommendation_outcomes'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recommendation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('strategy_recommendations.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('campaigns.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    metric_before: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metric_after: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
