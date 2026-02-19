import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProviderQuotaState(Base):
    __tablename__ = "provider_quota_states"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "environment",
            "provider_name",
            "capability",
            "window_start",
            name="uq_provider_quota_tenant_env_provider_capability_window_start",
        ),
        CheckConstraint("limit_count >= 0", name="ck_provider_quota_limit_non_negative"),
        CheckConstraint("used_count >= 0", name="ck_provider_quota_used_non_negative"),
        CheckConstraint("remaining_count >= 0", name="ck_provider_quota_remaining_non_negative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(20), nullable=False, default="production")
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False)
    capability: Mapped[str] = mapped_column(String(80), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    limit_count: Mapped[int] = mapped_column(Integer, nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remaining_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_exhausted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
