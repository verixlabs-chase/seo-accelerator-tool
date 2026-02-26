import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StrategyAutomationEvent(Base):
    __tablename__ = 'strategy_automation_events'
    __table_args__ = (
        Index('ix_strategy_automation_events_campaign_evaluation_date', 'campaign_id', 'evaluation_date'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False, index=True)
    evaluation_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    prior_phase: Mapped[str] = mapped_column(String(64), nullable=False)
    new_phase: Mapped[str] = mapped_column(String(64), nullable=False)
    triggered_rules: Mapped[str] = mapped_column(Text, nullable=False, default='[]')
    momentum_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default='{}')
    action_summary: Mapped[str] = mapped_column(Text, nullable=False, default='{}')
    version_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
