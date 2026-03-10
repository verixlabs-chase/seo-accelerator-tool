from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IndustrySimilarityMatrix(Base):
    __tablename__ = 'industry_similarity_matrix'

    similarity_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    source_industry_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target_industry_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    transfer_allowed: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
