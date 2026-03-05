import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IntelligenceMetricsSnapshot(Base):
    __tablename__ = 'intelligence_metrics_snapshots'
    __table_args__ = (
        UniqueConstraint('campaign_id', 'metric_date', name='uq_intelligence_metrics_snapshot_campaign_date'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('campaigns.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    signals_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    features_computed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    patterns_detected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recommendations_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    executions_run: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    positive_outcomes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_outcomes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    policy_updates_applied: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)
