import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PolicyFeatureEdge(Base):
    __tablename__ = 'policy_feature_edges'
    __table_args__ = (
        UniqueConstraint('policy_id', 'feature_name', 'industry', name='uq_policy_feature_edge_identity'),
        Index('ix_policy_feature_edges_industry_confidence', 'industry', 'confidence'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    feature_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    effect_size: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    industry: Mapped[str] = mapped_column(String(120), nullable=False, default='unknown', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class FeatureImpactEdge(Base):
    __tablename__ = 'causal_feature_edges'
    __table_args__ = (
        UniqueConstraint('policy_id', 'feature_name', 'outcome_name', 'industry', name='uq_causal_feature_edge_identity'),
        Index('ix_causal_feature_edges_industry_confidence', 'industry', 'confidence'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    feature_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    outcome_name: Mapped[str] = mapped_column(String(255), nullable=False, default='outcome::success', index=True)
    effect_size: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    industry: Mapped[str] = mapped_column(String(120), nullable=False, default='unknown', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
