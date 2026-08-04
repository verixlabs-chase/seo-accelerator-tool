from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KeywordResearchRun(Base):
    __tablename__ = "keyword_research_runs"
    __table_args__ = (
        Index(
            "ix_keyword_research_runs_campaign_created",
            "campaign_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
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
        String(36), ForeignKey("business_locations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="complete")
    location_name: Mapped[str] = mapped_column(String(255), nullable=False)
    language_code: Mapped[str] = mapped_column(String(12), nullable=False, default="en")
    sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    suggestion_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_reported_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )


class KeywordResearchSuggestion(Base):
    __tablename__ = "keyword_research_suggestions"
    __table_args__ = (
        UniqueConstraint("run_id", "normalized_keyword", name="uq_keyword_research_run_keyword"),
        Index(
            "ix_keyword_research_suggestions_campaign_group_score",
            "campaign_id",
            "opportunity_group",
            "opportunity_score",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("keyword_research_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
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
        String(36), ForeignKey("business_locations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    source_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    search_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cpc: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    competition: Mapped[float | None] = mapped_column(Float, nullable=True)
    competition_level: Mapped[str | None] = mapped_column(String(24), nullable=True)
    keyword_difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_searches: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    current_position: Mapped[float | None] = mapped_column(Float, nullable=True)
    gsc_clicks: Mapped[float | None] = mapped_column(Float, nullable=True)
    gsc_impressions: Mapped[float | None] = mapped_column(Float, nullable=True)
    gsc_position: Mapped[float | None] = mapped_column(Float, nullable=True)
    intent: Mapped[str] = mapped_column(String(40), nullable=False)
    opportunity_group: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    relevance_score: Mapped[int] = mapped_column(Integer, nullable=False)
    relevance_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="needs_review", index=True
    )
    matched_service_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("business_services.id", ondelete="SET NULL"), nullable=True
    )
    matched_service_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    matched_service_area_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("business_service_areas.id", ondelete="SET NULL"), nullable=True
    )
    matched_service_area_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    area_match_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    ai_review_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_requested", index=True
    )
    ai_relevance_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ai_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("governed_ai_runs.id", ondelete="SET NULL"), nullable=True
    )
    ai_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    relevance_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    opportunity_score: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    recommended_action: Mapped[str] = mapped_column(String(160), nullable=False)
    recommendation_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    tracked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )


class KeywordRelevanceFeedback(Base):
    __tablename__ = "keyword_relevance_feedback"
    __table_args__ = (
        CheckConstraint(
            "decision in ('relevant','unrelated','cleared')",
            name="ck_keyword_relevance_feedback_decision",
        ),
        Index(
            "ix_keyword_relevance_feedback_campaign_keyword_created",
            "campaign_id",
            "normalized_keyword",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
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
    suggestion_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("keyword_research_suggestions.id", ondelete="SET NULL"),
        nullable=True,
    )
    service_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("business_services.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="owner")
    rules_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
