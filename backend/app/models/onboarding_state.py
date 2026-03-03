from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


ONBOARDING_STATE_INIT = "INIT"
ONBOARDING_STATE_ORG_PROVISIONED = "ORG_PROVISIONED"
ONBOARDING_STATE_ENTITLEMENTS_CREATED = "ENTITLEMENTS_CREATED"
ONBOARDING_STATE_LEDGER_INITIALIZED = "LEDGER_INITIALIZED"
ONBOARDING_STATE_PORTFOLIO_CREATED = "PORTFOLIO_CREATED"
ONBOARDING_STATE_PROVIDER_BASELINE_READY = "PROVIDER_BASELINE_READY"
ONBOARDING_STATE_BASELINE_SYNC_COMPLETE = "BASELINE_SYNC_COMPLETE"
ONBOARDING_STATE_ACTIVE = "ACTIVE"
ONBOARDING_STATE_SUSPENDED = "SUSPENDED"


class OnboardingState(Base):
    __tablename__ = "onboarding_states"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_onboarding_state_org"),
        Index("ix_onboarding_state_organization_id", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(String(50), nullable=False)
    last_transition_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    deterministic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
