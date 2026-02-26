import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SQLEnum, Float, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TemporalSignalType(str, Enum):
    RANK = 'rank'
    REVIEW = 'review'
    COMPETITOR = 'competitor'
    CONTENT = 'content'
    AUTHORITY = 'authority'
    TRAFFIC = 'traffic'
    CONVERSION = 'conversion'
    CUSTOM = 'custom'


class TemporalSignalSnapshot(Base):
    __tablename__ = 'temporal_signal_snapshots'
    __table_args__ = (
        Index('ix_temporal_signal_snapshots_campaign_observed_at', 'campaign_id', 'observed_at'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False, index=True)
    signal_type: Mapped[TemporalSignalType] = mapped_column(
        SQLEnum(TemporalSignalType, name='temporal_signal_type', native_enum=False, validate_strings=True),
        nullable=False,
        index=True,
    )
    metric_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    metric_value: Mapped[float] = mapped_column(Numeric(18, 6, asdecimal=False), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    version_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class MomentumMetric(Base):
    __tablename__ = 'momentum_metrics'
    __table_args__ = (
        Index('ix_momentum_metrics_campaign_computed_at', 'campaign_id', 'computed_at'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    slope: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    acceleration: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    volatility: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    deterministic_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_version: Mapped[str] = mapped_column(String(64), nullable=False)


class StrategyPhaseHistory(Base):
    __tablename__ = 'strategy_phase_history'
    __table_args__ = (
        Index('ix_strategy_phase_history_campaign_effective_date', 'campaign_id', 'effective_date'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False, index=True)
    prior_phase: Mapped[str] = mapped_column(String(64), nullable=False)
    new_phase: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    momentum_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    version_hash: Mapped[str] = mapped_column(String(128), nullable=False)
