import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutreachCampaign(Base):
    __tablename__ = "outreach_campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class OutreachContact(Base):
    __tablename__ = "outreach_contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    outreach_campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("outreach_campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class BacklinkOpportunity(Base):
    __tablename__ = "backlink_opportunities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(320), nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Backlink(Base):
    __tablename__ = "backlinks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="live")
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    directory_name: Mapped[str] = mapped_column(String(255), nullable=False)
    submission_status: Mapped[str] = mapped_column(String(40), nullable=False, default="submitted")
    listing_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class DirectoryListing(Base):
    __tablename__ = "directory_listings"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "business_location_id",
            "source_key",
            "external_id",
            name="uq_directory_listings_location_source_external",
        ),
        CheckConstraint(
            "status in ('correct','inconsistent','missing','duplicate','submitted','live','verified','unavailable')",
            name="ck_directory_listings_status",
        ),
        CheckConstraint(
            "directory_importance in ('essential','important','standard','unknown')",
            name="ck_directory_listings_importance",
        ),
        Index(
            "ix_directory_listings_location_status",
            "business_location_id",
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
        String(36), ForeignKey("business_locations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    source_name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    listing_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="live", index=True)
    business_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_category: Mapped[str | None] = mapped_column(String(160), nullable=True)
    observed_fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    field_differences: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    directory_importance: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class DirectoryListingObservation(Base):
    __tablename__ = "directory_listing_observations"
    __table_args__ = (
        UniqueConstraint(
            "listing_id",
            "evidence_digest",
            name="uq_dir_listing_obs_listing_digest",
        ),
        Index(
            "ix_dir_listing_obs_listing_observed",
            "listing_id",
            "observed_at",
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
    listing_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("directory_listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    observed_fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    field_differences: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
