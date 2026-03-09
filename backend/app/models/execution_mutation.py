from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExecutionMutation(Base):
    __tablename__ = 'execution_mutations'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    execution_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('recommendation_executions.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    recommendation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False, default='wordpress_plugin', index=True)
    mutation_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_url: Mapped[str] = mapped_column(String(500), nullable=False)
    external_mutation_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    mutation_payload: Mapped[str] = mapped_column(Text, nullable=False, default='{}')
    before_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='planned', index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)
