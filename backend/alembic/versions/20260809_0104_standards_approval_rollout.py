"""add standards approvals and controlled rollouts

Revision ID: 20260809_0104
Revises: 20260809_0103
Create Date: 2026-08-09 18:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260809_0104"
down_revision = "20260809_0103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "standards_approvals",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column(
            "replay_report_id",
            sa.String(36),
            sa.ForeignKey("standards_replay_reports.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("replay_seal_digest", sa.String(64), nullable=False),
        sa.Column("candidate_content_hash", sa.String(64), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("rollout_plan_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("rollback_plan_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "acknowledges_new_baseline",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("decided_by_user_id", sa.String(36), nullable=False),
        sa.Column(
            "automatic_activation_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision in ('approved','rejected')",
            name="ck_standards_approvals_decision",
        ),
    )
    for name, columns in (
        ("ix_standards_approvals_replay_report_id", ["replay_report_id"]),
        ("ix_standards_approvals_decision", ["decision"]),
        ("ix_standards_approvals_created_at", ["created_at"]),
        (
            "ix_standards_approvals_report_created",
            ["replay_report_id", "created_at"],
        ),
    ):
        op.create_index(name, "standards_approvals", columns)

    op.create_table(
        "standards_rollouts",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column(
            "approval_id",
            sa.String(36),
            sa.ForeignKey("standards_approvals.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("artifact_type", sa.String(40), nullable=False),
        sa.Column("artifact_key", sa.String(180), nullable=False),
        sa.Column("base_version", sa.String(40), nullable=False),
        sa.Column("candidate_version", sa.String(40), nullable=False),
        sa.Column("rollout_mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="scheduled"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "provider_metric_contract_version_id",
            sa.String(36),
            sa.ForeignKey("provider_metric_contract_versions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "previous_provider_metric_contract_version_id",
            sa.String(36),
            sa.ForeignKey("provider_metric_contract_versions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "reference_library_version_id",
            sa.String(36),
            sa.ForeignKey("reference_library_versions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "previous_reference_library_version_id",
            sa.String(36),
            sa.ForeignKey("reference_library_versions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("rolled_back_by_user_id", sa.String(36), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_reason", sa.Text(), nullable=True),
        sa.Column(
            "automatic_activation_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "rollout_mode in ('immediate','scheduled')",
            name="ck_standards_rollouts_mode",
        ),
        sa.CheckConstraint(
            "status in ('scheduled','in_progress','completed','failed','rolled_back')",
            name="ck_standards_rollouts_status",
        ),
    )
    for name, columns in (
        ("ix_standards_rollouts_approval_id", ["approval_id"]),
        ("ix_standards_rollouts_artifact_type", ["artifact_type"]),
        ("ix_standards_rollouts_artifact_key", ["artifact_key"]),
        ("ix_standards_rollouts_status", ["status"]),
        ("ix_standards_rollouts_scheduled_for", ["scheduled_for"]),
        ("ix_standards_rollouts_created_at", ["created_at"]),
        (
            "ix_standards_rollouts_status_scheduled",
            ["status", "scheduled_for"],
        ),
        (
            "ix_standards_rollouts_artifact_created",
            ["artifact_type", "artifact_key", "created_at"],
        ),
    ):
        op.create_index(name, "standards_rollouts", columns)


def downgrade() -> None:
    op.drop_table("standards_rollouts")
    op.drop_table("standards_approvals")
