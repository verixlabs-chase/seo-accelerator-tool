from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProductionCapabilityProof(Base):
    """Append-only production proof for one marketed commercial capability."""

    __tablename__ = "production_capability_proofs"
    __table_args__ = (
        CheckConstraint(
            "result in ('proven','limited','unavailable')",
            name="ck_production_capability_proofs_result",
        ),
        CheckConstraint(
            "expires_at > observed_at",
            name="ck_production_capability_proofs_expiry",
        ),
        UniqueConstraint("evidence_digest", name="uq_production_capability_proofs_digest"),
        Index(
            "ix_production_capability_proofs_code_observed",
            "capability_code",
            "observed_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    schema_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="ops1-capability-proof-v1"
    )
    capability_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    customer_limitation: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
