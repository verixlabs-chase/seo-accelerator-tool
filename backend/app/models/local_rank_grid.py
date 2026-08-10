from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LocalRankGridRun(Base):
    __tablename__ = "local_rank_grid_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_local_rank_grid_runs_org_idempotency",
        ),
        CheckConstraint(
            "status in ('queued','submitting','pending','partial','completed','failed')",
            name="ck_local_rank_grid_runs_status",
        ),
        CheckConstraint(
            "grid_size in (3,5,7)",
            name="ck_local_rank_grid_runs_grid_size",
        ),
        CheckConstraint(
            "radius_miles >= 1 and radius_miles <= 25",
            name="ck_local_rank_grid_runs_radius",
        ),
        Index(
            "ix_local_rank_grid_runs_campaign_created",
            "campaign_id",
            "created_at",
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
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    grid_size: Mapped[int] = mapped_column(Integer, nullable=False)
    radius_miles: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    center_latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    center_longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    provider_location_code: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_location_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_location_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    keyword_snapshot: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    keyword_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_checks: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_checks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_checks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_found_checks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="standard_queue"
    )
    credential_owner: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reservation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cost_ledger_entries.id", ondelete="SET NULL"), nullable=True
    )
    estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    provider_reported_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8), nullable=True
    )
    estimated_credit_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_domain: Mapped[str | None] = mapped_column(String(320), nullable=True)
    source_name: Mapped[str] = mapped_column(
        String(64), nullable=False, default="google_maps_results"
    )
    metric_contract_id: Mapped[str] = mapped_column(
        String(180), nullable=False, default="local_grid.position"
    )
    metric_contract_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0")
    grid_definition_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="legacy")
    language_code: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    device_class: Mapped[str] = mapped_column(String(20), nullable=False, default="provider_default")
    provider_method: Mapped[str] = mapped_column(String(80), nullable=False, default="maps_search")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class LocalRankGridPoint(Base):
    __tablename__ = "local_rank_grid_points"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "keyword_id",
            "grid_index",
            name="uq_local_rank_grid_points_run_keyword_index",
        ),
        CheckConstraint(
            "status in ('queued','pending','ranked','not_found','failed')",
            name="ck_local_rank_grid_points_status",
        ),
        CheckConstraint(
            "rank is null or rank >= 1",
            name="ck_local_rank_grid_points_rank",
        ),
        Index(
            "ix_local_rank_grid_points_run_keyword",
            "run_id",
            "keyword_id",
            "grid_index",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("local_rank_grid_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    keyword_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("campaign_keywords.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    grid_index: Mapped[int] = mapped_column(Integer, nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    column_index: Mapped[int] = mapped_column(Integer, nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_business_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    matched_business_domain: Mapped[str | None] = mapped_column(String(320), nullable=True)
    source_name: Mapped[str] = mapped_column(
        String(64), nullable=False, default="google_maps_results"
    )
    metric_contract_id: Mapped[str] = mapped_column(
        String(180), nullable=False, default="local_grid.position"
    )
    metric_contract_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0")
    scope_key: Mapped[str] = mapped_column(String(64), nullable=False, default="legacy")
    provider_task_id: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)
    provider_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_status_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_reported_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
