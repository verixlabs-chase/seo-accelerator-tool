from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PortfolioFleetRun(Base):
    """Approval-gated parent record for work fanned across location portfolios."""

    __tablename__ = "portfolio_fleet_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "request_key",
            name="uq_portfolio_fleet_runs_org_request_key",
        ),
        Index(
            "ix_portfolio_fleet_runs_org_created",
            "organization_id",
            "created_at",
        ),
        Index(
            "ix_portfolio_fleet_runs_org_status",
            "organization_id",
            "status",
        ),
        CheckConstraint(
            "status in ('awaiting_approval','blocked','running','succeeded','partial','failed','cancelled')",
            name="ck_portfolio_fleet_runs_status",
        ),
        CheckConstraint("version >= 1", name="ck_portfolio_fleet_runs_version"),
        CheckConstraint(
            "estimated_credit_units >= 0",
            name="ck_portfolio_fleet_runs_estimated_credits",
        ),
        CheckConstraint(
            "target_count >= 0 and ready_count >= 0 and blocked_count >= 0 and "
            "queued_count >= 0 and running_count >= 0 and succeeded_count >= 0 and "
            "failed_count >= 0",
            name="ck_portfolio_fleet_runs_nonnegative_counts",
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
    target_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("portfolio_target_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action_key: Mapped[str] = mapped_column(String(80), nullable=False)
    request_key: Mapped[str] = mapped_column(String(120), nullable=False)
    target_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="awaiting_approval", index=True
    )
    preflight_json: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    target_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queued_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    running_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_credit_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items = relationship(
        "PortfolioFleetRunItem",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PortfolioFleetRunItem(Base):
    """One location's independently recoverable part of a portfolio run."""

    __tablename__ = "portfolio_fleet_run_items"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_fleet_run_id",
            "business_location_id",
            name="uq_portfolio_fleet_run_items_run_location",
        ),
        UniqueConstraint(
            "portfolio_fleet_run_id",
            "item_key",
            name="uq_portfolio_fleet_run_items_run_key",
        ),
        Index(
            "ix_portfolio_fleet_run_items_run_status",
            "portfolio_fleet_run_id",
            "status",
        ),
        CheckConstraint(
            "status in ('ready','blocked','queued','running','succeeded','failed')",
            name="ck_portfolio_fleet_run_items_status",
        ),
        CheckConstraint("retries >= 0", name="ck_portfolio_fleet_run_items_retries"),
        CheckConstraint(
            "estimated_credit_units >= 0",
            name="ck_portfolio_fleet_run_items_estimated_credits",
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
    portfolio_fleet_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("portfolio_fleet_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("business_locations.id", ondelete="RESTRICT"), nullable=False
    )
    campaign_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    portfolio_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True
    )
    fleet_job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("fleet_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    item_key: Mapped[str] = mapped_column(String(160), nullable=False)
    location_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ready")
    capability_json: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    estimated_credit_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    run = relationship("PortfolioFleetRun", back_populates="items")
