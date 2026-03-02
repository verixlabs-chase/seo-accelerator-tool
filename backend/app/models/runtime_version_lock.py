from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RuntimeVersionLock(Base):
    __tablename__ = "runtime_version_locks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    expected_schema_revision: Mapped[str] = mapped_column(String(40), nullable=False)
    expected_code_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False)
    expected_registry_version: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
