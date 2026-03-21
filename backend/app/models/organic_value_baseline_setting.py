from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrganicValueBaselineSetting(Base):
    __tablename__ = "organic_value_baseline_settings"
    __table_args__ = (
        UniqueConstraint("campaign_id", name="uq_organic_value_baseline_settings_campaign_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    monthly_seo_investment: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    monthly_seo_investment_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unavailable")
    monthly_seo_investment_source_type: Mapped[str] = mapped_column(String(24), nullable=False, default="unavailable")
    updated_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    monthly_seo_investment_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
