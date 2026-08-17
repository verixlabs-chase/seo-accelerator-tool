from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CommercialFeatureActivation(Base):
    __tablename__ = "commercial_feature_activations"
    __table_args__ = (
        CheckConstraint(
            "state IN ('observe', 'enforced')",
            name="ck_commercial_feature_activations_state",
        ),
    )

    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    catalog_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
