from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PortfolioPolicyType(str, Enum):
    EXECUTION = "execution"
    REPORTING = "reporting"
    GOVERNANCE = "governance"


class PortfolioPolicy(Base):
    __tablename__ = "portfolio_policies"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "policy_type", name="uq_portfolio_policies_portfolio_type"),
        Index("ix_portfolio_policies_portfolio_updated_at", "portfolio_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    portfolio_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_type: Mapped[PortfolioPolicyType] = mapped_column(
        SAEnum(PortfolioPolicyType, name="portfolio_policy_type", native_enum=False),
        nullable=False,
    )
    policy_json: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    portfolio = relationship("Portfolio", back_populates="policies")
