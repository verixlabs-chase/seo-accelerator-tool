from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PortfolioStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_portfolios_org_code"),
        Index("ix_portfolios_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[PortfolioStatus] = mapped_column(
        SAEnum(PortfolioStatus, name="portfolio_status", native_enum=False),
        nullable=False,
        default=PortfolioStatus.ACTIVE,
        index=True,
    )
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="UTC")
    default_sla_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    locations = relationship("Location", back_populates="portfolio", passive_deletes=True)
    policies = relationship("PortfolioPolicy", back_populates="portfolio", cascade="all, delete-orphan", passive_deletes=True)
    fleet_jobs = relationship("FleetJob", back_populates="portfolio", cascade="all, delete-orphan", passive_deletes=True)
