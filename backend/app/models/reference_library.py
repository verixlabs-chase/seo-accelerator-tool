import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReferenceLibraryVersion(Base):
    __tablename__ = "reference_library_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "version", name="uq_reference_library_version_tenant_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class ReferenceLibraryArtifact(Base):
    __tablename__ = "reference_library_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "reference_library_version_id",
            "artifact_type",
            name="uq_reference_library_artifact_type",
        ),
        Index("ix_ref_lib_artifacts_version_id", "reference_library_version_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    reference_library_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reference_library_versions.id", ondelete="CASCADE"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(40), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class ReferenceLibraryValidationRun(Base):
    __tablename__ = "reference_library_validation_runs"
    __table_args__ = (
        Index("ix_ref_lib_validation_runs_version_id", "reference_library_version_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    reference_library_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reference_library_versions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    errors_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class ReferenceLibraryActivation(Base):
    __tablename__ = "reference_library_activations"
    __table_args__ = (Index("ix_ref_lib_activations_version_id", "reference_library_version_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    reference_library_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reference_library_versions.id", ondelete="CASCADE"), nullable=False
    )
    activated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rollback_from_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    activation_status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class ReferenceLibraryStandardsCheck(Base):
    __tablename__ = "reference_library_standards_checks"
    __table_args__ = (
        Index("ix_reference_library_standards_checks_source_observed", "source_id", "observed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    lexicon_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    source_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    drift_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )


class StandardsSourceRegistry(Base):
    """Platform-owned allow-list of authoritative standards sources."""

    __tablename__ = "standards_source_registry"

    source_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_owner: Mapped[str] = mapped_column(String(120), nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    source_format: Mapped[str] = mapped_column(String(30), nullable=False)
    source_scope: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    review_interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_source_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_normalized_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )


class StandardsSourceSnapshot(Base):
    """Immutable response evidence for one authoritative standards source."""

    __tablename__ = "standards_source_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "source_digest",
            name="uq_standards_source_snapshot_digest",
        ),
        Index("ix_standards_source_snapshots_source_observed", "source_id", "observed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("standards_source_registry.source_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    source_format: Mapped[str] = mapped_column(String(30), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_modified: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    content_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )


class StandardsChangeCandidate(Base):
    """A deterministic, review-only interpretation of one official-source change."""

    __tablename__ = "standards_change_candidates"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "current_snapshot_id",
            name="uq_standards_change_source_snapshot",
        ),
        Index("ix_standards_change_status_created", "status", "created_at"),
        Index("ix_standards_change_source_created", "source_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("standards_source_registry.source_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    previous_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("standards_source_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    current_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("standards_source_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    classification_version: Mapped[str] = mapped_column(String(40), nullable=False)
    change_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    materiality: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="needs_review", index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    diff_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    classification_reasons_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    review_disposition: Mapped[str | None] = mapped_column(String(40), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class StandardsImpactLink(Base):
    """One product surface that may be affected by a standards change candidate."""

    __tablename__ = "standards_impact_links"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id",
            "impact_type",
            "impact_key",
            name="uq_standards_impact_candidate_key",
        ),
        Index("ix_standards_impact_candidate_blocking", "candidate_id", "is_blocking"),
        Index("ix_standards_impact_type_key", "impact_type", "impact_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("standards_change_candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    impact_type: Mapped[str] = mapped_column(String(60), nullable=False)
    impact_key: Mapped[str] = mapped_column(String(160), nullable=False)
    impact_reason: Mapped[str] = mapped_column(Text, nullable=False)
    risk_state: Mapped[str] = mapped_column(String(30), nullable=False)
    is_blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
