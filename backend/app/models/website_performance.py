from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WebsitePerformanceMeasurement(Base):
    __tablename__ = "website_performance_measurements"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_website_performance_measurements_idempotency_key",
        ),
        Index(
            "ix_website_performance_campaign_history",
            "campaign_id",
            "form_factor",
            "source",
            "captured_at",
        ),
        Index(
            "ix_website_performance_tenant_status",
            "tenant_id",
            "status",
            "captured_at",
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
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    measured_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="url")
    form_factor: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    lcp_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    inp_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    cls_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    ttfb_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    fcp_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    tbt_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    performance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    collection_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    collection_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lexicon_id: Mapped[str] = mapped_column(String(120), nullable=False)
    lexicon_version: Mapped[str] = mapped_column(String(80), nullable=False)
    fallback_to_origin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    distribution: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    diagnostics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

