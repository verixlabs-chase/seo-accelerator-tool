from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProviderPriceCard(Base):
    __tablename__ = "provider_price_cards"
    __table_args__ = (
        UniqueConstraint(
            "provider_name",
            "capability",
            "operation",
            "model_name",
            "version",
            name="uq_provider_price_card_identity",
        ),
        Index(
            "ix_provider_price_cards_lookup",
            "provider_name",
            "capability",
            "operation",
            "active",
            "effective_from",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False)
    capability: Mapped[str] = mapped_column(String(80), nullable=False)
    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, default=Decimal("0"))
    input_token_cost_per_million: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    cached_input_token_cost_per_million: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    output_token_cost_per_million: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class CostLedgerEntry(Base):
    """Append-only currency events for provider and future AI work."""

    __tablename__ = "cost_ledger_entries"
    __table_args__ = (
        CheckConstraint(
            "credential_owner in ('platform','organization')",
            name="ck_cost_ledger_credential_owner",
        ),
        CheckConstraint(
            "event_type in ('reservation','reconciliation','release')",
            name="ck_cost_ledger_event_type",
        ),
        CheckConstraint(
            "status in ('reserved','reconciled','released')",
            name="ck_cost_ledger_status",
        ),
        CheckConstraint("quantity >= 0", name="ck_cost_ledger_quantity_nonnegative"),
        CheckConstraint("estimated_cost >= 0", name="ck_cost_ledger_estimated_nonnegative"),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            "event_type",
            name="uq_cost_ledger_org_key_event",
        ),
        Index("ix_cost_ledger_org_created", "organization_id", "created_at"),
        Index("ix_cost_ledger_org_status", "organization_id", "status"),
        Index("ix_cost_ledger_reservation", "reservation_id"),
        Index(
            "ix_cost_ledger_provider_created",
            "provider_name",
            "capability",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    business_location_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    campaign_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("campaigns.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False)
    capability: Mapped[str] = mapped_column(String(80), nullable=False)
    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    credential_owner: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    provider_reported_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    budget_impact_cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    reservation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    price_card_version: Mapped[str] = mapped_column(String(80), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(40), nullable=False)
    plan_revenue_snapshot: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class OrganizationCostAllocation(Base):
    """Versioned monthly non-provider COGS entered by platform operators."""

    __tablename__ = "organization_cost_allocations"
    __table_args__ = (
        CheckConstraint("hosting_cost >= 0", name="ck_org_cost_hosting_nonnegative"),
        CheckConstraint("storage_cost >= 0", name="ck_org_cost_storage_nonnegative"),
        CheckConstraint("email_cost >= 0", name="ck_org_cost_email_nonnegative"),
        CheckConstraint("support_cost >= 0", name="ck_org_cost_support_nonnegative"),
        CheckConstraint("other_cost >= 0", name="ck_org_cost_other_nonnegative"),
        UniqueConstraint(
            "organization_id",
            "period_start",
            "version",
            name="uq_org_cost_allocation_period_version",
        ),
        Index(
            "ix_org_cost_allocations_period",
            "organization_id",
            "period_start",
            "version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    revenue_override: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    hosting_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    storage_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    email_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    support_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    other_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="operator")
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
