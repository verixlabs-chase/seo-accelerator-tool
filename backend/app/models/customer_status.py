from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CustomerStatusUpdate(Base):
    """Append-only, customer-safe update for a platform incident or maintenance window."""

    __tablename__ = "customer_status_updates"
    __table_args__ = (
        CheckConstraint(
            "state in ('investigating','identified','monitoring','resolved','maintenance')",
            name="ck_customer_status_updates_state",
        ),
        CheckConstraint(
            "impact in ('none','minor','major','critical')",
            name="ck_customer_status_updates_impact",
        ),
        CheckConstraint("update_number > 0", name="ck_customer_status_updates_number"),
        CheckConstraint(
            "ends_at is null or ends_at > starts_at",
            name="ck_customer_status_updates_window",
        ),
        UniqueConstraint(
            "incident_key",
            "update_number",
            name="uq_customer_status_updates_incident_number",
        ),
        UniqueConstraint("content_digest", name="uq_customer_status_updates_digest"),
        Index(
            "ix_customer_status_updates_incident_created",
            "incident_key",
            "created_at",
        ),
        Index(
            "ix_customer_status_updates_visible_created",
            "visible_to_customers",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    schema_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="ops1-customer-status-v1"
    )
    incident_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    update_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    impact: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    affected_surfaces: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    visible_to_customers: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
