"""add provider execution telemetry persistence tables

Revision ID: 20260219_0017
Revises: 20260218_0016
Create Date: 2026-02-19 10:15:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260219_0017"
down_revision = "20260218_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_health_states",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False, server_default="production"),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("provider_version", sa.String(length=40), nullable=True),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("breaker_state", sa.String(length=20), nullable=False, server_default="closed"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_rate_1h", sa.Float(), nullable=True),
        sa.Column("p95_latency_ms_1h", sa.Integer(), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "environment",
            "provider_name",
            "capability",
            name="uq_provider_health_tenant_env_provider_capability",
        ),
    )
    op.create_index("ix_provider_health_states_tenant_id", "provider_health_states", ["tenant_id"])
    op.create_index(
        "ix_provider_health_states_tenant_env_breaker_state",
        "provider_health_states",
        ["tenant_id", "environment", "breaker_state"],
    )

    op.create_table(
        "provider_quota_states",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False, server_default="production"),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("limit_count", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remaining_count", sa.Integer(), nullable=False),
        sa.Column("last_exhausted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "environment",
            "provider_name",
            "capability",
            "window_start",
            name="uq_provider_quota_tenant_env_provider_capability_window_start",
        ),
        sa.CheckConstraint("limit_count >= 0", name="ck_provider_quota_limit_non_negative"),
        sa.CheckConstraint("used_count >= 0", name="ck_provider_quota_used_non_negative"),
        sa.CheckConstraint("remaining_count >= 0", name="ck_provider_quota_remaining_non_negative"),
    )
    op.create_index("ix_provider_quota_states_tenant_id", "provider_quota_states", ["tenant_id"])
    op.create_index(
        "ix_provider_quota_states_tenant_env_window_end",
        "provider_quota_states",
        ["tenant_id", "environment", "window_end"],
    )

    op.create_table(
        "provider_execution_metrics",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False, server_default="production"),
        sa.Column("task_execution_id", sa.String(length=36), sa.ForeignKey("task_executions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("provider_version", sa.String(length=40), nullable=True),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("timeout_budget_ms", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=40), nullable=True),
        sa.Column("error_severity", sa.String(length=20), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_provider_execution_metrics_tenant_id", "provider_execution_metrics", ["tenant_id"])
    op.create_index(
        "ix_pem_tenant_provider_cap_created",
        "provider_execution_metrics",
        ["tenant_id", "provider_name", "capability", "created_at"],
    )
    op.create_index(
        "ix_provider_execution_metrics_tenant_outcome_created_at",
        "provider_execution_metrics",
        ["tenant_id", "outcome", "created_at"],
    )
    op.create_index(
        "ix_provider_execution_metrics_correlation_id",
        "provider_execution_metrics",
        ["correlation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_execution_metrics_correlation_id", table_name="provider_execution_metrics")
    op.drop_index("ix_provider_execution_metrics_tenant_outcome_created_at", table_name="provider_execution_metrics")
    op.drop_index(
        "ix_pem_tenant_provider_cap_created",
        table_name="provider_execution_metrics",
    )
    op.drop_index("ix_provider_execution_metrics_tenant_id", table_name="provider_execution_metrics")
    op.drop_table("provider_execution_metrics")

    op.drop_index("ix_provider_quota_states_tenant_env_window_end", table_name="provider_quota_states")
    op.drop_index("ix_provider_quota_states_tenant_id", table_name="provider_quota_states")
    op.drop_table("provider_quota_states")

    op.drop_index("ix_provider_health_states_tenant_env_breaker_state", table_name="provider_health_states")
    op.drop_index("ix_provider_health_states_tenant_id", table_name="provider_health_states")
    op.drop_table("provider_health_states")
