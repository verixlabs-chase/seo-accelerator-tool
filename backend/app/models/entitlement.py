from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EntitlementValueType(str, Enum):
    INTEGER = "integer"
    BOOLEAN = "boolean"
    UNLIMITED = "unlimited"


class EntitlementResetPeriod(str, Enum):
    NONE = "none"
    DAILY = "daily"
    MONTHLY = "monthly"


_VALUE_TYPE_ENUM = SAEnum(
    EntitlementValueType,
    name="entitlement_value_type",
    native_enum=False,
    values_callable=lambda members: [member.value for member in members],
)

_RESET_PERIOD_ENUM = SAEnum(
    EntitlementResetPeriod,
    name="entitlement_reset_period",
    native_enum=False,
    values_callable=lambda members: [member.value for member in members],
)


class Entitlement(Base):
    __tablename__ = "entitlements"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_entitlements_org_code"),
        Index("ix_entitlements_organization_id", "organization_id"),
        Index("ix_entitlements_org_code", "organization_id", "code"),
        CheckConstraint(
            "((value_type = 'unlimited' AND limit_value IS NULL) OR (value_type != 'unlimited' AND limit_value IS NOT NULL))",
            name="ck_entitlements_limit_value_matches_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    value_type: Mapped[EntitlementValueType] = mapped_column(_VALUE_TYPE_ENUM, nullable=False)
    limit_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reset_period: Mapped[EntitlementResetPeriod] = mapped_column(
        _RESET_PERIOD_ENUM,
        nullable=False,
        default=EntitlementResetPeriod.NONE,
    )
    is_enforced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
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
