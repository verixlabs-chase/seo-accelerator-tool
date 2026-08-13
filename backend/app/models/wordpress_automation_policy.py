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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WordPressAutomationPolicy(Base):
    __tablename__ = "wordpress_automation_policies"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            name="uq_wordpress_automation_policies_campaign",
        ),
        CheckConstraint(
            "monthly_action_limit >= 0 and monthly_action_limit <= 500",
            name="ck_wordpress_automation_policies_monthly_limit",
        ),
        CheckConstraint(
            "risk_tier_ceiling >= 1 and risk_tier_ceiling <= 3",
            name="ck_wordpress_automation_policies_risk_ceiling",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_wordpress_automation_policies_version",
        ),
        Index(
            "ix_wordpress_automation_policies_org_enabled",
            "organization_id",
            "automation_enabled",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    automation_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    emergency_stop: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    paused_reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    paused_execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    allowed_action_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    allowed_url_prefixes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    schedule_timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    schedule_days: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    window_start_local: Mapped[str] = mapped_column(String(5), nullable=False, default="00:00")
    window_end_local: Mapped[str] = mapped_column(String(5), nullable=False, default="23:59")
    blackout_windows: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    monthly_action_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_tier_ceiling: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    requires_manual_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
