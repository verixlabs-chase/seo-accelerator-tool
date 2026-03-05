import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RecommendationExecution(Base):
    __tablename__ = 'recommendation_executions'

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
    execution_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    execution_payload: Mapped[str] = mapped_column(Text, nullable=False, default='{}')
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    deterministic_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='pending', index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default='medium')
    scope_of_change: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    historical_success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)
