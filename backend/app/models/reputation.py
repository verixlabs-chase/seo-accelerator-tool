from __future__ import annotations

from datetime import UTC, datetime
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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


class ReputationReview(Base):
    __tablename__ = "reputation_reviews"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "business_location_id",
            "source_key",
            "external_review_id",
            name="uq_reputation_reviews_location_source_external",
        ),
        CheckConstraint(
            "source_type in ('owned_profile','public_competitor')",
            name="ck_reputation_reviews_source_type",
        ),
        CheckConstraint(
            "response_status in ('unanswered','responded','removed','unavailable')",
            name="ck_reputation_reviews_response_status",
        ),
        CheckConstraint(
            "rating >= 1 and rating <= 5",
            name="ck_reputation_reviews_rating",
        ),
        Index(
            "ix_reputation_reviews_location_response",
            "business_location_id",
            "response_status",
        ),
        Index(
            "ix_reputation_reviews_campaign_reviewed",
            "campaign_id",
            "reviewed_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    source_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    external_review_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_resource_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    response_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unanswered", index=True
    )
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    provider_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class ReputationReviewObservation(Base):
    __tablename__ = "reputation_review_observations"
    __table_args__ = (
        UniqueConstraint(
            "review_id",
            "evidence_digest",
            name="uq_reputation_review_obs_review_digest",
        ),
        Index(
            "ix_reputation_review_obs_review_captured",
            "review_id",
            "captured_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    review_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reputation_reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class ReputationResponsePolicy(Base):
    __tablename__ = "reputation_response_policies"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "version",
            name="uq_reputation_response_policies_org_version",
        ),
        CheckConstraint(
            "status in ('active','inactive')",
            name="ck_reputation_response_policies_status",
        ),
        Index(
            "ix_reputation_response_policies_org_status",
            "organization_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="draft_only")
    rules: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rules_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class ReputationResponseDraft(Base):
    __tablename__ = "reputation_response_drafts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_reputation_response_drafts_org_idempotency",
        ),
        CheckConstraint(
            "status in ('human_required','ready_for_review','approved','rejected','unavailable')",
            name="ck_reputation_response_drafts_status",
        ),
        CheckConstraint(
            "risk_class in ('standard','sensitive')",
            name="ck_reputation_response_drafts_risk_class",
        ),
        Index(
            "ix_reputation_response_drafts_review_created",
            "review_id",
            "created_at",
        ),
        Index(
            "ix_reputation_response_drafts_campaign_status",
            "campaign_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    review_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reputation_reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reputation_response_policies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    governed_ai_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("governed_ai_runs.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    risk_class: Mapped[str] = mapped_column(String(24), nullable=False)
    sensitive_topics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    review_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    draft_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class ReputationProviderCapability(Base):
    __tablename__ = "reputation_provider_capabilities"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "capability",
            name="uq_reputation_provider_capabilities_connection_capability",
        ),
        CheckConstraint(
            "status in ('validation_authorized','verified','revoked')",
            name="ck_reputation_provider_capabilities_status",
        ),
        Index(
            "ix_reputation_provider_capabilities_org_status",
            "organization_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("data_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False)
    capability: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_method: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    proof_type: Mapped[str] = mapped_column(String(80), nullable=False)
    proof_reference: Mapped[str] = mapped_column(Text, nullable=False)
    authorized_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    authorized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReputationResponseExecution(Base):
    __tablename__ = "reputation_response_executions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_reputation_response_executions_org_idempotency",
        ),
        UniqueConstraint(
            "draft_id",
            name="uq_reputation_response_executions_draft",
        ),
        CheckConstraint(
            "status in ('queued','posting','retrying','posted','paused','blocked','failed','cancelled')",
            name="ck_reputation_response_executions_status",
        ),
        Index(
            "ix_reputation_response_executions_campaign_status",
            "campaign_id",
            "status",
        ),
        Index(
            "ix_reputation_response_executions_review_created",
            "review_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("business_locations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reputation_reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    draft_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reputation_response_drafts.id", ondelete="RESTRICT"), nullable=False
    )
    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("data_connections.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    capability_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reputation_provider_capabilities.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    platform_job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("platform_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    approved_text: Mapped[str] = mapped_column(Text, nullable=False)
    approved_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    approval_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    review_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    capability_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confirmation_version: Mapped[str] = mapped_column(String(80), nullable=False)
    confirmation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_method: Mapped[str] = mapped_column(String(160), nullable=False)
    external_review_resource_name: Mapped[str] = mapped_column(Text, nullable=False)
    provider_reply_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider_policy_violation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider_receipt: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
