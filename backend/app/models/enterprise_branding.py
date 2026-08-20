import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrganizationReportBrand(Base):
    __tablename__ = "organization_report_brands"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_org_report_brands_org"),
        CheckConstraint("tenant_id = organization_id", name="ck_org_report_brands_scope"),
        CheckConstraint("version >= 1", name="ck_org_report_brands_version"),
        Index("ix_org_report_brands_tenant", "tenant_id"),
        Index("ix_org_report_brands_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    brand_name: Mapped[str] = mapped_column(String(120), nullable=False)
    report_title: Mapped[str] = mapped_column(String(120), nullable=False)
    footer_text: Mapped[str] = mapped_column(String(240), nullable=False)
    hide_platform_attribution: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
