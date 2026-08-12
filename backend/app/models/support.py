from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SupportRequest(Base):
    """Tenant-scoped customer support request with an explicitly consented safe snapshot."""

    __tablename__ = "support_requests"
    __table_args__ = (
        Index("ix_support_requests_org_status_created", "organization_id", "status", "created_at"),
        Index("ix_support_requests_status_target", "status", "response_target_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    reference_code: Mapped[str] = mapped_column(String(24), nullable=False, unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    campaign_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    page_path: Mapped[str] = mapped_column(String(80), nullable=False)
    customer_summary: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(24), nullable=False, default="standard", index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="received", index=True)
    diagnostic_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    operator_access_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    operator_access_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    diagnostic_bundle: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status_history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    response_target_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
