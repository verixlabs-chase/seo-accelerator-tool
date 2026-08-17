from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OnboardingBaseline(Base):
    """Immutable first-measurement record for one campaign and location."""

    __tablename__ = "onboarding_baselines"
    __table_args__ = (
        CheckConstraint(
            "status in ('ready','limited')",
            name="ck_onboarding_baselines_status",
        ),
        CheckConstraint(
            "evidence_window_days = 28",
            name="ck_onboarding_baselines_window_days",
        ),
        UniqueConstraint(
            "campaign_id",
            "baseline_number",
            name="uq_onboarding_baselines_campaign_number",
        ),
        UniqueConstraint(
            "baseline_hash",
            name="uq_onboarding_baselines_hash",
        ),
        ForeignKeyConstraint(
            ["campaign_id", "tenant_id", "organization_id", "business_location_id"],
            [
                "campaigns.id",
                "campaigns.tenant_id",
                "campaigns.organization_id",
                "campaigns.business_location_id",
            ],
            name="fk_onboarding_baselines_campaign_scope",
            ondelete="CASCADE",
        ),
        Index(
            "ix_onboarding_baselines_scope_generated",
            "tenant_id",
            "organization_id",
            "campaign_id",
            "generated_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
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
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    business_location_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
    )
    report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("monthly_reports.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    generated_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    baseline_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_window_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=28
    )
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_states: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    score_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    diagnosis_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    report_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
