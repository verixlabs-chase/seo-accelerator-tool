from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BusinessLocation(Base):
    __tablename__ = "business_locations"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_business_locations_org_name"),
        UniqueConstraint("id", "organization_id", name="uq_business_locations_id_org"),
        Index("ix_business_locations_organization_id", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    sub_account_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("sub_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    primary_city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="US")
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    coordinate_precision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    coordinate_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_location_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_location_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_location_resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
