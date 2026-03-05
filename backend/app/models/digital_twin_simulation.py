import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DigitalTwinSimulation(Base):
    __tablename__ = 'digital_twin_simulations'
    __table_args__ = (
        Index('ix_digital_twin_simulations_campaign_id', 'campaign_id'),
        Index('ix_digital_twin_simulations_created_at', 'created_at'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('campaigns.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    strategy_actions: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    predicted_rank_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    predicted_traffic_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    expected_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    selected_strategy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False, default='v1')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)
