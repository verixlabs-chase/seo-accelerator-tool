import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        Index("ix_organization_tier_profile_id", "tier_profile_id"),
        Index(
            "ix_organizations_stripe_customer_id",
            "stripe_customer_id",
            unique=True,
        ),
        Index(
            "ix_organizations_stripe_subscription_id",
            "stripe_subscription_id",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    plan_type: Mapped[str] = mapped_column(String(30), nullable=False, default="standard", index=True)
    billing_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="subscription", index=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_price_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_last_checkout_request_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    billing_last_checkout_session_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    billing_last_checkout_plan_code: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    billing_pending_checkout_request_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    billing_pending_checkout_session_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    billing_pending_checkout_plan_code: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    billing_pending_checkout_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    billing_subscription_status: Mapped[str | None] = mapped_column(
        String(40), nullable=True
    )
    billing_subscription_event_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    billing_subscription_event_type: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    billing_payment_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    billing_payment_event_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    billing_payment_event_type: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    billing_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    billing_current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    billing_cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    billing_last_event_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    billing_last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    tier_profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tier_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tier_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
