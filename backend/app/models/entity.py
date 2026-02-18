import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PageEntity(Base):
    __tablename__ = "page_entities"
    __table_args__ = (UniqueConstraint("crawl_page_result_id", "entity", name="uq_page_entities_result_entity"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    page_id: Mapped[str] = mapped_column(String(36), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True)
    crawl_page_result_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("crawl_page_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="page")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class CompetitorEntity(Base):
    __tablename__ = "competitor_entities"
    __table_args__ = (UniqueConstraint("competitor_page_id", "entity", name="uq_competitor_entities_page_entity"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    competitor_id: Mapped[str] = mapped_column(String(36), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False, index=True)
    competitor_page_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("competitor_pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="serp_snapshot")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class EntityAnalysisRun(Base):
    __tablename__ = "entity_analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    entity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    overlap_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    campaign_entity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    competitor_entity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_entities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    recommendations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
