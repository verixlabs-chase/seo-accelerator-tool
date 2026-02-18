"""add reference library foundation tables

Revision ID: 20260218_0011
Revises: 20260217_0010
Create Date: 2026-02-18 20:30:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260218_0011"
down_revision = "20260217_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reference_library_versions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "version", name="uq_reference_library_version_tenant_version"),
    )
    op.create_index("ix_reference_library_versions_tenant_id", "reference_library_versions", ["tenant_id"])
    op.create_index("ix_reference_library_versions_updated_at", "reference_library_versions", ["updated_at"])

    op.create_table(
        "reference_library_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column(
            "reference_library_version_id",
            sa.String(length=36),
            sa.ForeignKey("reference_library_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("artifact_type", sa.String(length=40), nullable=False),
        sa.Column("artifact_uri", sa.Text(), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "reference_library_version_id",
            "artifact_type",
            name="uq_reference_library_artifact_type",
        ),
    )
    op.create_index("ix_reference_library_artifacts_tenant_id", "reference_library_artifacts", ["tenant_id"])
    op.create_index(
        "ix_ref_lib_artifacts_version_id",
        "reference_library_artifacts",
        ["reference_library_version_id"],
    )
    op.create_index("ix_reference_library_artifacts_created_at", "reference_library_artifacts", ["created_at"])

    op.create_table(
        "reference_library_validation_runs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column(
            "reference_library_version_id",
            sa.String(length=36),
            sa.ForeignKey("reference_library_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("errors_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reference_library_validation_runs_tenant_id", "reference_library_validation_runs", ["tenant_id"])
    op.create_index(
        "ix_ref_lib_validation_runs_version_id",
        "reference_library_validation_runs",
        ["reference_library_version_id"],
    )
    op.create_index("ix_reference_library_validation_runs_executed_at", "reference_library_validation_runs", ["executed_at"])

    op.create_table(
        "reference_library_activations",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column(
            "reference_library_version_id",
            sa.String(length=36),
            sa.ForeignKey("reference_library_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("activated_by", sa.String(length=36), nullable=True),
        sa.Column("rollback_from_version", sa.String(length=40), nullable=True),
        sa.Column("activation_status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reference_library_activations_tenant_id", "reference_library_activations", ["tenant_id"])
    op.create_index(
        "ix_ref_lib_activations_version_id",
        "reference_library_activations",
        ["reference_library_version_id"],
    )
    op.create_index("ix_reference_library_activations_created_at", "reference_library_activations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_reference_library_activations_created_at", table_name="reference_library_activations")
    op.drop_index("ix_ref_lib_activations_version_id", table_name="reference_library_activations")
    op.drop_index("ix_reference_library_activations_tenant_id", table_name="reference_library_activations")
    op.drop_table("reference_library_activations")

    op.drop_index("ix_reference_library_validation_runs_executed_at", table_name="reference_library_validation_runs")
    op.drop_index("ix_ref_lib_validation_runs_version_id", table_name="reference_library_validation_runs")
    op.drop_index("ix_reference_library_validation_runs_tenant_id", table_name="reference_library_validation_runs")
    op.drop_table("reference_library_validation_runs")

    op.drop_index("ix_reference_library_artifacts_created_at", table_name="reference_library_artifacts")
    op.drop_index("ix_ref_lib_artifacts_version_id", table_name="reference_library_artifacts")
    op.drop_index("ix_reference_library_artifacts_tenant_id", table_name="reference_library_artifacts")
    op.drop_table("reference_library_artifacts")

    op.drop_index("ix_reference_library_versions_updated_at", table_name="reference_library_versions")
    op.drop_index("ix_reference_library_versions_tenant_id", table_name="reference_library_versions")
    op.drop_table("reference_library_versions")
