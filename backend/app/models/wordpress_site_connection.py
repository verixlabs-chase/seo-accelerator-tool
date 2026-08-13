import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WordPressSiteConnection(Base):
    __tablename__ = "wordpress_site_connections"
    __table_args__ = (
        UniqueConstraint("campaign_id", name="uq_wordpress_site_connections_campaign"),
        UniqueConstraint("pairing_code_hash", name="uq_wordpress_site_connections_pairing_hash"),
        CheckConstraint(
            "status in ('pending','connected','disconnected')",
            name="ck_wordpress_site_connections_status",
        ),
        Index(
            "ix_wordpress_site_connections_org_status",
            "organization_id",
            "status",
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
    site_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    pairing_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pairing_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    encrypted_secret_blob: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    key_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    plugin_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    paired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
