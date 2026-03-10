import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PolicyPerformance(Base):
    __tablename__ = 'policy_performance'
    __table_args__ = (
        UniqueConstraint('policy_id', 'campaign_id', 'industry', name='uq_policy_performance_scope'),
        Index('ix_policy_performance_industry_success', 'industry', 'success_score'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('campaigns.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    industry: Mapped[str] = mapped_column(String(120), nullable=False, default='unknown', index=True)
    success_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    execution_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)
