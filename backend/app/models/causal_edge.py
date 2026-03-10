import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CausalEdge(Base):
    __tablename__ = 'causal_edges'
    __table_args__ = (
        UniqueConstraint('source_node', 'target_node', 'policy_id', 'industry', name='uq_causal_edge_identity'),
        Index('ix_causal_edges_industry_confidence', 'industry', 'confidence'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_node: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_node: Mapped[str] = mapped_column(String(255), nullable=False)
    policy_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    effect_size: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    industry: Mapped[str] = mapped_column(String(120), nullable=False, default='unknown', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
