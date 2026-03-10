import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StrategyEvolutionLog(Base):
    __tablename__ = 'strategy_evolution_logs'
    __table_args__ = (
        UniqueConstraint('parent_policy', 'new_policy', name='uq_strategy_evolution_log_policy_pair'),
        Index('ix_strategy_evolution_logs_parent_created', 'parent_policy', 'created_at'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_policy: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    new_policy: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    mutation_type: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
