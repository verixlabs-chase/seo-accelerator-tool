import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProviderHealthState(Base):
    __tablename__ = "provider_health_states"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "environment",
            "provider_name",
            "capability",
            name="uq_provider_health_tenant_env_provider_capability",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(20), nullable=False, default="production")
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    capability: Mapped[str] = mapped_column(String(80), nullable=False)
    breaker_state: Mapped[str] = mapped_column(String(20), nullable=False, default="closed")
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rate_1h: Mapped[float | None] = mapped_column(Float, nullable=True)
    p95_latency_ms_1h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
