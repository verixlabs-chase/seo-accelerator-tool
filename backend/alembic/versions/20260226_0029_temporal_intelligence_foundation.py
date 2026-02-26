"""temporal intelligence foundation

Revision ID: 20260226_0029
Revises: 20260224_0028
Create Date: 2026-02-26 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260226_0029"
down_revision = "20260224_0028"
branch_labels = None
depends_on = None


temporal_signal_type_enum = sa.Enum(
    "rank",
    "review",
    "competitor",
    "content",
    "authority",
    "traffic",
    "conversion",
    "custom",
    name="temporal_signal_type",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "temporal_signal_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("signal_type", temporal_signal_type_enum, nullable=False),
        sa.Column("metric_name", sa.String(length=120), nullable=False),
        sa.Column("metric_value", sa.Numeric(precision=18, scale=6, asdecimal=False), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("version_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_temporal_signal_snapshots_campaign_id", "temporal_signal_snapshots", ["campaign_id"], unique=False)
    op.create_index("ix_temporal_signal_snapshots_signal_type", "temporal_signal_snapshots", ["signal_type"], unique=False)
    op.create_index("ix_temporal_signal_snapshots_metric_name", "temporal_signal_snapshots", ["metric_name"], unique=False)
    op.create_index("ix_temporal_signal_snapshots_observed_at", "temporal_signal_snapshots", ["observed_at"], unique=False)
    op.create_index(
        "ix_temporal_signal_snapshots_campaign_observed_at",
        "temporal_signal_snapshots",
        ["campaign_id", "observed_at"],
        unique=False,
    )

    op.create_table(
        "momentum_metrics",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("metric_name", sa.String(length=120), nullable=False),
        sa.Column("slope", sa.Float(), nullable=False),
        sa.Column("acceleration", sa.Float(), nullable=False),
        sa.Column("volatility", sa.Float(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deterministic_hash", sa.String(length=128), nullable=False),
        sa.Column("profile_version", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_momentum_metrics_campaign_id", "momentum_metrics", ["campaign_id"], unique=False)
    op.create_index("ix_momentum_metrics_metric_name", "momentum_metrics", ["metric_name"], unique=False)
    op.create_index("ix_momentum_metrics_computed_at", "momentum_metrics", ["computed_at"], unique=False)
    op.create_index("ix_momentum_metrics_campaign_computed_at", "momentum_metrics", ["campaign_id", "computed_at"], unique=False)

    op.create_table(
        "strategy_phase_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("prior_phase", sa.String(length=64), nullable=False),
        sa.Column("new_phase", sa.String(length=64), nullable=False),
        sa.Column("trigger_reason", sa.String(length=255), nullable=False),
        sa.Column("momentum_score", sa.Float(), nullable=False),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version_hash", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_strategy_phase_history_campaign_id", "strategy_phase_history", ["campaign_id"], unique=False)
    op.create_index("ix_strategy_phase_history_effective_date", "strategy_phase_history", ["effective_date"], unique=False)
    op.create_index(
        "ix_strategy_phase_history_campaign_effective_date",
        "strategy_phase_history",
        ["campaign_id", "effective_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_phase_history_campaign_effective_date", table_name="strategy_phase_history")
    op.drop_index("ix_strategy_phase_history_effective_date", table_name="strategy_phase_history")
    op.drop_index("ix_strategy_phase_history_campaign_id", table_name="strategy_phase_history")
    op.drop_table("strategy_phase_history")

    op.drop_index("ix_momentum_metrics_campaign_computed_at", table_name="momentum_metrics")
    op.drop_index("ix_momentum_metrics_computed_at", table_name="momentum_metrics")
    op.drop_index("ix_momentum_metrics_metric_name", table_name="momentum_metrics")
    op.drop_index("ix_momentum_metrics_campaign_id", table_name="momentum_metrics")
    op.drop_table("momentum_metrics")

    op.drop_index("ix_temporal_signal_snapshots_campaign_observed_at", table_name="temporal_signal_snapshots")
    op.drop_index("ix_temporal_signal_snapshots_observed_at", table_name="temporal_signal_snapshots")
    op.drop_index("ix_temporal_signal_snapshots_metric_name", table_name="temporal_signal_snapshots")
    op.drop_index("ix_temporal_signal_snapshots_signal_type", table_name="temporal_signal_snapshots")
    op.drop_index("ix_temporal_signal_snapshots_campaign_id", table_name="temporal_signal_snapshots")
    op.drop_table("temporal_signal_snapshots")
