"""add standards candidate versions and replay reports

Revision ID: 20260809_0103
Revises: 20260809_0102
Create Date: 2026-08-09 16:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260809_0103"
down_revision = "20260809_0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("provider_metric_contract_versions") as batch_op:
        batch_op.add_column(
            sa.Column("lifecycle_status", sa.String(24), nullable=False, server_default="active")
        )
        batch_op.add_column(sa.Column("supersedes_version_id", sa.String(36), nullable=True))
        batch_op.add_column(
            sa.Column("standards_change_candidate_id", sa.String(36), nullable=True)
        )
        batch_op.add_column(sa.Column("proposed_by_user_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_provider_metric_contract_versions_supersedes_version_id",
            "provider_metric_contract_versions",
            ["supersedes_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_provider_metric_contract_versions_standards_change_candidate_id",
            "standards_change_candidates",
            ["standards_change_candidate_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_check_constraint(
            "ck_provider_metric_contract_versions_lifecycle_status",
            "lifecycle_status in ('active','candidate','retired')",
        )
        batch_op.create_index(
            "ix_provider_metric_contract_versions_lifecycle_status", ["lifecycle_status"]
        )
        batch_op.create_index(
            "ix_provider_metric_contract_versions_supersedes_version_id",
            ["supersedes_version_id"],
        )
        batch_op.create_index(
            "ix_provider_metric_contract_versions_standards_change_candidate_id",
            ["standards_change_candidate_id"],
        )

    op.create_table(
        "standards_replay_reports",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column(
            "standards_change_candidate_id",
            sa.String(36),
            sa.ForeignKey("standards_change_candidates.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "provider_metric_contract_version_id",
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
        sa.Column("artifact_type", sa.String(40), nullable=False),
        sa.Column("artifact_key", sa.String(180), nullable=False),
        sa.Column("base_version", sa.String(40), nullable=False),
        sa.Column("candidate_version", sa.String(40), nullable=False),
        sa.Column("replay_version", sa.String(40), nullable=False),
        sa.Column("fixture_set_version", sa.String(40), nullable=False),
        sa.Column("sample_type", sa.String(30), nullable=False),
        sa.Column("sample_digest", sa.String(64), nullable=False),
        sa.Column("approval_reference_digest", sa.String(64), nullable=True),
        sa.Column("tenant_safe_sample", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changed_diagnoses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changed_actions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changed_forecasts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changed_results", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("newly_unknown_results", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalidated_comparisons", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requires_new_baseline", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("definition_diff_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("impact_report_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("replay_results_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "automatic_activation_allowed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("executed_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "artifact_type in ('provider_metric_contract','intelligence_lexicon')",
            name="ck_standards_replay_reports_artifact_type",
        ),
        sa.CheckConstraint(
            "sample_type in ('fixed_fixture','approved_evidence','combined')",
            name="ck_standards_replay_reports_sample_type",
        ),
        sa.CheckConstraint(
            "status in ('passed','changed','blocked','failed')",
            name="ck_standards_replay_reports_status",
        ),
    )
    for name, columns in (
        ("ix_standards_replay_reports_standards_change_candidate_id", ["standards_change_candidate_id"]),
        (
            "ix_standards_replay_reports_provider_metric_contract_version_id",
            ["provider_metric_contract_version_id"],
        ),
        ("ix_standards_replay_reports_reference_library_version_id", ["reference_library_version_id"]),
        ("ix_standards_replay_reports_artifact_type", ["artifact_type"]),
        ("ix_standards_replay_reports_artifact_key", ["artifact_key"]),
        ("ix_standards_replay_reports_status", ["status"]),
        ("ix_standards_replay_reports_created_at", ["created_at"]),
        (
            "ix_standards_replay_reports_artifact_created",
            ["artifact_type", "artifact_key", "created_at"],
        ),
        (
            "ix_standards_replay_reports_change_created",
            ["standards_change_candidate_id", "created_at"],
        ),
    ):
        op.create_index(name, "standards_replay_reports", columns)


def downgrade() -> None:
    op.drop_table("standards_replay_reports")
    with op.batch_alter_table("provider_metric_contract_versions") as batch_op:
        batch_op.drop_index("ix_provider_metric_contract_versions_standards_change_candidate_id")
        batch_op.drop_index("ix_provider_metric_contract_versions_supersedes_version_id")
        batch_op.drop_index("ix_provider_metric_contract_versions_lifecycle_status")
        batch_op.drop_constraint(
            "fk_provider_metric_contract_versions_standards_change_candidate_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_provider_metric_contract_versions_supersedes_version_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "ck_provider_metric_contract_versions_lifecycle_status", type_="check"
        )
        for column in (
            "proposed_at",
            "proposed_by_user_id",
            "standards_change_candidate_id",
            "supersedes_version_id",
            "lifecycle_status",
        ):
            batch_op.drop_column(column)
