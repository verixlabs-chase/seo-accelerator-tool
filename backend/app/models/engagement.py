from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AchievementGrant(Base):
    """Evidence-backed, deterministic customer achievement."""

    __tablename__ = "achievement_grants"
    __table_args__ = (
        CheckConstraint(
            "category in ('foundation','habit','verified_result','multi_location')",
            name="ck_achievement_grants_category",
        ),
        CheckConstraint(
            "scope_type in ('location','organization')",
            name="ck_achievement_grants_scope_type",
        ),
        UniqueConstraint(
            "tenant_id",
            "rule_key",
            "rule_version",
            "scope_type",
            "scope_id",
            name="uq_achievement_grants_rule_scope",
        ),
        Index(
            "ix_achievement_grants_org_earned",
            "organization_id",
            "earned_at",
        ),
        Index(
            "ix_achievement_grants_location_earned",
            "business_location_id",
            "earned_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_location_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rule_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(24), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    qualified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class AchievementPreference(Base):
    """Optional celebration and notification choices without deleting history."""

    __tablename__ = "achievement_preferences"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            name="uq_achievement_preferences_tenant_user",
        ),
        Index(
            "ix_achievement_preferences_org_user",
            "organization_id",
            "user_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    celebrations_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
