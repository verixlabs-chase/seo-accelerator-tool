import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrganizationProviderCredential(Base):
    __tablename__ = "organization_provider_credentials"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider_name",
            name="uq_org_provider_credentials_org_provider",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False)
    auth_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    encrypted_secret_blob: Mapped[str] = mapped_column(Text, nullable=False)
    key_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    key_version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
