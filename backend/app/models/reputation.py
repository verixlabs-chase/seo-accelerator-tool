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
        String(36), ForeignKey("business_locations.id", ondelete="CASCADE"), nullable=False, index=True
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
    response_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
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
        String(36), ForeignKey("business_locations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reputation_reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
