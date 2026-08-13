from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WordPressChangePreview(Base):
    __tablename__ = "wordpress_change_previews"
    __table_args__ = (
        CheckConstraint(
            "status in ('ready','blocked','approved','superseded')",
            name="ck_wordpress_change_previews_status",
        ),
        UniqueConstraint(
            "execution_id",
            "preview_hash",
            name="uq_wordpress_change_previews_execution_hash",
        ),
        Index(
            "ix_wordpress_change_previews_execution_created",
            "execution_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    execution_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("recommendation_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recommendation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("strategy_recommendations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    preview_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ready", index=True)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    affected_url_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mutation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
