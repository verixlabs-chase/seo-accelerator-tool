import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (Index("ix_organization_tier_profile_id", "tier_profile_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    plan_type: Mapped[str] = mapped_column(String(30), nullable=False, default="standard", index=True)
    billing_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="subscription", index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    tier_profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tier_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tier_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
