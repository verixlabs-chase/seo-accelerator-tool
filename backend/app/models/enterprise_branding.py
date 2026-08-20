import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrganizationReportBrand(Base):
    __tablename__ = "organization_report_brands"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_org_report_brands_org"),
        CheckConstraint("tenant_id = organization_id", name="ck_org_report_brands_scope"),
        CheckConstraint("version >= 1", name="ck_org_report_brands_version"),
        CheckConstraint(
            "length(accent_color) = 7 AND substr(accent_color, 1, 1) = '#'",
            name="ck_org_report_brands_accent",
        ),
        CheckConstraint(
            "(logo_content IS NULL AND logo_sha256 IS NULL AND logo_width IS NULL "
            "AND logo_height IS NULL AND logo_updated_at IS NULL) OR "
            "(logo_content IS NOT NULL AND logo_sha256 IS NOT NULL AND logo_width IS NOT NULL "
            "AND logo_height IS NOT NULL AND logo_updated_at IS NOT NULL)",
            name="ck_org_report_brands_logo_complete",
        ),
        CheckConstraint(
            "logo_content IS NULL OR (length(logo_content) >= 1 AND length(logo_content) <= 65536)",
            name="ck_org_report_brands_logo_size",
        ),
        CheckConstraint(
            "logo_content IS NULL OR (length(logo_sha256) = 64 "
            "AND logo_width BETWEEN 16 AND 1600 AND logo_height BETWEEN 16 AND 1600 "
            "AND logo_width * logo_height <= 1000000)",
            name="ck_org_report_brands_logo_dimensions",
        ),
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
    accent_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#E85D19")
    logo_content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    logo_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    logo_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    logo_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
