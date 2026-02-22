from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FleetJobType(str, Enum):
    CRAWL = "crawl"
    RANK = "rank"
    REPORT = "report"
    ONBOARD = "onboard"
    SCHEDULE = "schedule"
    PAUSE = "pause"
    RESUME = "resume"
    REMEDIATE = "remediate"


class FleetJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FleetJob(Base):
    __tablename__ = "fleet_jobs"
    __table_args__ = (
        Index("ix_fleet_jobs_portfolio_created_at", "portfolio_id", "created_at"),
        Index("ix_fleet_jobs_org_status_created_at", "organization_id", "status", "created_at"),
        Index("ix_fleet_jobs_portfolio_jobtype_idempotency", "portfolio_id", "job_type", "idempotency_key"),
        UniqueConstraint("portfolio_id", "job_type", "idempotency_key", name="uq_fleet_jobs_portfolio_job_type_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    portfolio_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_type: Mapped[FleetJobType] = mapped_column(
        SAEnum(
            FleetJobType,
            name="fleet_job_type",
            native_enum=False,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[FleetJobStatus] = mapped_column(
        SAEnum(
            FleetJobStatus,
            name="fleet_job_status",
            native_enum=False,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    request_payload: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    summary_json: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    total_items: Mapped[int] = mapped_column(nullable=False, default=0)
    queued_items: Mapped[int] = mapped_column(nullable=False, default=0)
    running_items: Mapped[int] = mapped_column(nullable=False, default=0)
    succeeded_items: Mapped[int] = mapped_column(nullable=False, default=0)
    failed_items: Mapped[int] = mapped_column(nullable=False, default=0)
    cancelled_items: Mapped[int] = mapped_column(nullable=False, default=0)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    portfolio = relationship("Portfolio", back_populates="fleet_jobs")
    items = relationship("FleetJobItem", back_populates="fleet_job", cascade="all, delete-orphan", passive_deletes=True)

    __mapper_args__ = {
        "version_id_col": version,
    }
