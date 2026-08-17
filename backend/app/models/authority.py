import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutreachCampaign(Base):
    __tablename__ = "outreach_campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class OutreachContact(Base):
    __tablename__ = "outreach_contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    outreach_campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("outreach_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class AuthorityOutreachDraft(Base):
    __tablename__ = "authority_outreach_drafts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_authority_outreach_drafts_org_idempotency",
        ),
        CheckConstraint(
            "source_type in ('competitor_gap','lost_link','unlinked_mention')",
            name="ck_authority_outreach_drafts_source_type",
        ),
        CheckConstraint(
            "status in ('draft','reviewed','closed')",
            name="ck_authority_outreach_drafts_status",
        ),
        Index(
            "ix_authority_outreach_drafts_campaign_created",
            "campaign_id",
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
    business_location_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recommendation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("strategy_recommendations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    referring_domain: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    contact_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str] = mapped_column(String(180), nullable=False)
    message_body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    owner_confirmed_recipient: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class BacklinkOpportunity(Base):
    __tablename__ = "backlink_opportunities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(320), nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class Backlink(Base):
    __tablename__ = "backlinks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="live")
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class AuthorityGapResearchRun(Base):
    __tablename__ = "authority_gap_research_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_authority_gap_runs_org_idempotency",
        ),
        CheckConstraint(
            "status in ('running','complete','partial','failed')",
            name="ck_authority_gap_runs_status",
        ),
        CheckConstraint(
            "result_limit >= 1 and result_limit <= 1000",
            name="ck_authority_gap_runs_result_limit",
        ),
        Index(
            "ix_authority_gap_runs_campaign_created",
            "campaign_id",
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
    business_location_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", index=True)
    owner_domain: Mapped[str] = mapped_column(String(320), nullable=False)
    competitors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    result_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False, default="live_link_index")
    reservation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cost_ledger_entries.id", ondelete="SET NULL"), nullable=True
    )
    provider_reported_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthorityLinkGap(Base):
    __tablename__ = "authority_link_gaps"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "source_url",
            name="uq_authority_link_gaps_run_source",
        ),
        CheckConstraint(
            "relevance_classification in "
            "('service_and_area_match','service_match','area_match','needs_review')",
            name="ck_authority_link_gaps_relevance_classification",
        ),
        Index("ix_authority_link_gaps_campaign_observed", "campaign_id", "observed_at"),
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
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("authority_gap_research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    referring_domain: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_page_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    competitor_matches: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    relevance_classification: Mapped[str] = mapped_column(
        String(32), nullable=False, default="needs_review", index=True
    )
    matched_services: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    matched_service_areas: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    relevance_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class AuthorityLinkChangeRun(Base):
    __tablename__ = "authority_link_change_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_authority_link_change_runs_org_idempotency",
        ),
        CheckConstraint(
            "status in ('running','complete','partial','failed')",
            name="ck_authority_link_change_runs_status",
        ),
        CheckConstraint(
            "result_limit_per_state >= 1 and result_limit_per_state <= 500",
            name="ck_authority_link_change_runs_limit",
        ),
        Index(
            "ix_authority_link_change_runs_campaign_created",
            "campaign_id",
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
    business_location_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", index=True)
    owner_domain: Mapped[str] = mapped_column(String(320), nullable=False)
    result_limit_per_state: Mapped[int] = mapped_column(Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False, default="live_link_index")
    reservation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cost_ledger_entries.id", ondelete="SET NULL"), nullable=True
    )
    provider_reported_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    new_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lost_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthorityLinkChange(Base):
    __tablename__ = "authority_link_changes"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "change_state",
            "source_url",
            "target_url",
            name="uq_authority_link_changes_run_state_source_target",
        ),
        CheckConstraint(
            "change_state in ('new','lost')",
            name="ck_authority_link_changes_state",
        ),
        Index("ix_authority_link_changes_campaign_observed", "campaign_id", "observed_at"),
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
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("authority_link_change_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    change_state: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    referring_domain: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_page_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    link_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dofollow: Mapped[bool] = mapped_column(nullable=False, default=False)
    anchor: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class AuthorityInventoryRun(Base):
    __tablename__ = "authority_inventory_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_authority_inventory_runs_org_idempotency",
        ),
        CheckConstraint(
            "status in ('running','complete','partial','failed')",
            name="ck_authority_inventory_runs_status",
        ),
        CheckConstraint(
            "link_limit >= 1 and link_limit <= 1000",
            name="ck_authority_inventory_runs_link_limit",
        ),
        CheckConstraint(
            "mention_limit >= 1 and mention_limit <= 100",
            name="ck_authority_inventory_runs_mention_limit",
        ),
        Index(
            "ix_authority_inventory_runs_campaign_created",
            "campaign_id",
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
    business_location_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", index=True)
    owner_domain: Mapped[str] = mapped_column(String(320), nullable=False)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    link_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    mention_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False, default="live_web_index")
    reservation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cost_ledger_entries.id", ondelete="SET NULL"), nullable=True
    )
    provider_reported_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    link_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mention_candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unlinked_mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthorityInventoryLink(Base):
    __tablename__ = "authority_inventory_links"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "source_url",
            "target_url",
            name="uq_authority_inventory_links_run_source_target",
        ),
        Index("ix_authority_inventory_links_campaign_observed", "campaign_id", "observed_at"),
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
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("authority_inventory_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    referring_domain: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_page_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    link_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dofollow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    anchor: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class AuthorityUnlinkedMention(Base):
    __tablename__ = "authority_unlinked_mentions"
    __table_args__ = (
        UniqueConstraint("run_id", "source_url", name="uq_authority_unlinked_mentions_run_source"),
        CheckConstraint(
            "relevance_classification in "
            "('service_and_area_match','service_match','area_match','needs_review')",
            name="ck_authority_unlinked_mentions_relevance_classification",
        ),
        Index("ix_authority_unlinked_mentions_campaign_observed", "campaign_id", "observed_at"),
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
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("authority_inventory_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    referring_domain: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_page_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    mentioned_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relevance_classification: Mapped[str] = mapped_column(
        String(32), nullable=False, default="needs_review", index=True
    )
    matched_services: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    matched_service_areas: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    relevance_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    directory_name: Mapped[str] = mapped_column(String(255), nullable=False)
    submission_status: Mapped[str] = mapped_column(String(40), nullable=False, default="submitted")
    listing_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


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
        String(36),
        ForeignKey("business_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_type: Mapped[str] = mapped_column(
        String(24), nullable=False, default="live_collection", index=True
    )
    source_system: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_claimed_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    import_batch_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("migration_import_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
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
        String(36),
        ForeignKey("business_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    listing_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("directory_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    observed_fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    field_differences: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(
        String(24), nullable=False, default="live_collection", index=True
    )
    source_system: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_claimed_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    import_batch_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("migration_import_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class DirectoryListingDiscoveryRun(Base):
    __tablename__ = "directory_listing_discovery_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_dir_listing_discovery_org_idempotency",
        ),
        CheckConstraint(
            "status in ('queued','running','completed','failed')",
            name="ck_dir_listing_discovery_status",
        ),
        CheckConstraint(
            "credential_owner in ('platform','organization')",
            name="ck_dir_listing_discovery_credential_owner",
        ),
        CheckConstraint(
            "result_limit >= 1 and result_limit <= 100",
            name="ck_dir_listing_discovery_result_limit",
        ),
        Index(
            "ix_dir_listing_discovery_campaign_created",
            "campaign_id",
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
        String(36),
        ForeignKey("business_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    credential_owner: Mapped[str] = mapped_column(String(20), nullable=False)
    radius_km: Mapped[Decimal] = mapped_column(Numeric(9, 2), nullable=False)
    result_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    reservation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cost_ledger_entries.id", ondelete="SET NULL"), nullable=True
    )
    estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    provider_reported_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    estimated_credit_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
