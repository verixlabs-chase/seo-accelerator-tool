import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Experiment(Base):
    __tablename__ = 'experiments'

    experiment_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hypothesis: Mapped[str] = mapped_column(String(500), nullable=False)
    experiment_type: Mapped[str] = mapped_column(String(80), nullable=False, default='portfolio_policy')
    cohort_size: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='active', index=True)
    industry: Mapped[str] = mapped_column(String(120), nullable=False, default='unknown', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class ExperimentAssignment(Base):
    __tablename__ = 'experiment_assignments'
    __table_args__ = (
        UniqueConstraint('experiment_id', 'campaign_id', name='uq_experiment_assignment_campaign'),
        Index('ix_experiment_assignments_campaign_policy_created', 'campaign_id', 'assigned_policy_id', 'created_at'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[str] = mapped_column(String(36), ForeignKey('experiments.experiment_id', ondelete='CASCADE'), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False, index=True)
    cohort: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    bucket: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_policy_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class ExperimentOutcome(Base):
    __tablename__ = 'experiment_outcomes'
    __table_args__ = (
        UniqueConstraint('outcome_id', name='uq_experiment_outcome_source'),
        Index('ix_experiment_outcomes_experiment_measured', 'experiment_id', 'measured_at'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[str] = mapped_column(String(36), ForeignKey('experiments.experiment_id', ondelete='CASCADE'), nullable=False, index=True)
    assignment_id: Mapped[str] = mapped_column(String(36), ForeignKey('experiment_assignments.id', ondelete='CASCADE'), nullable=False, index=True)
    outcome_id: Mapped[str] = mapped_column(String(36), ForeignKey('recommendation_outcomes.id', ondelete='CASCADE'), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False, index=True)
    metric_before: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metric_after: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    success_flag: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
