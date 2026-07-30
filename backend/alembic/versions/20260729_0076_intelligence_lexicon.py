"""Persist intelligence lexicon payloads and standards drift checks.

Revision ID: 20260729_0076
Revises: 20260729_0075
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_0076"
down_revision = "20260729_0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reference_library_artifacts",
        sa.Column("payload_json", sa.Text(), nullable=True),
    )
    op.create_table(
        "reference_library_standards_checks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=False),
        sa.Column("lexicon_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("source_digest", sa.String(length=128), nullable=False),
        sa.Column("normalized_payload_json", sa.Text(), nullable=False),
        sa.Column("drift_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reference_library_standards_checks_source_id",
        "reference_library_standards_checks",
        ["source_id"],
    )
    op.create_index(
        "ix_reference_library_standards_checks_status",
        "reference_library_standards_checks",
        ["status"],
    )
    op.create_index(
        "ix_reference_library_standards_checks_observed_at",
        "reference_library_standards_checks",
        ["observed_at"],
    )
    op.create_index(
        "ix_reference_library_standards_checks_source_observed",
        "reference_library_standards_checks",
        ["source_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reference_library_standards_checks_source_observed",
        table_name="reference_library_standards_checks",
    )
    op.drop_index(
        "ix_reference_library_standards_checks_observed_at",
        table_name="reference_library_standards_checks",
    )
    op.drop_index(
        "ix_reference_library_standards_checks_status",
        table_name="reference_library_standards_checks",
    )
    op.drop_index(
        "ix_reference_library_standards_checks_source_id",
        table_name="reference_library_standards_checks",
    )
    op.drop_table("reference_library_standards_checks")
    op.drop_column("reference_library_artifacts", "payload_json")
