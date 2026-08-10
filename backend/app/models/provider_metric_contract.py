from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProviderMetricContractVersion(Base):
    """Platform-owned definition and comparison scope for one objective metric."""

    __tablename__ = "provider_metric_contract_versions"
    __table_args__ = (
        CheckConstraint(
            "collection_status in ('collected','derived','not_collected')",
            name="ck_provider_metric_contract_versions_collection_status",
        ),
        CheckConstraint(
            "direction in ('higher_is_better','lower_is_better','neutral','configuration')",
            name="ck_provider_metric_contract_versions_direction",
        ),
        CheckConstraint(
            "lifecycle_status in ('active','candidate','retired')",
            name="ck_provider_metric_contract_versions_lifecycle_status",
        ),
        UniqueConstraint(
            "contract_id",
            "version",
            name="uq_provider_metric_contract_versions_contract_version",
        ),
        Index(
            "ix_provider_metric_contract_versions_provider_family_active",
            "provider_name",
            "metric_family",
            "is_active",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    contract_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_family: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(String(60), nullable=False)
    aggregation: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    collection_status: Mapped[str] = mapped_column(String(24), nullable=False)
    authoritative_source_id: Mapped[str | None] = mapped_column(
        String(120),
        ForeignKey("standards_source_registry.source_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    required_scope_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    optional_scope_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    comparison_keys: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    freshness_days: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    lifecycle_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="active", index=True
    )
    supersedes_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("provider_metric_contract_versions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    standards_change_candidate_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("standards_change_candidates.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    proposed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    proposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
