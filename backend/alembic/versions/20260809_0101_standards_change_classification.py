"""add deterministic standards change candidates and impact links

Revision ID: 20260809_0101
Revises: 20260805_0100
Create Date: 2026-08-09 15:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260809_0101"
down_revision = "20260805_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "standards_change_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("previous_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("current_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("classification_version", sa.String(length=40), nullable=False),
        sa.Column("change_type", sa.String(length=80), nullable=False),
        sa.Column("materiality", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("diff_json", sa.Text(), nullable=False),
        sa.Column("classification_reasons_json", sa.Text(), nullable=False),
        sa.Column("automatic_activation_allowed", sa.Boolean(), nullable=False),
        sa.Column("review_disposition", sa.String(length=40), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["standards_source_registry.source_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_snapshot_id"],
            ["standards_source_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_snapshot_id"],
            ["standards_source_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "current_snapshot_id",
            name="uq_standards_change_source_snapshot",
        ),
    )
    op.create_index(
        "ix_standards_change_candidates_source_id",
        "standards_change_candidates",
        ["source_id"],
    )
    op.create_index(
        "ix_standards_change_candidates_current_snapshot_id",
        "standards_change_candidates",
        ["current_snapshot_id"],
    )
    op.create_index(
        "ix_standards_change_candidates_change_type",
        "standards_change_candidates",
        ["change_type"],
    )
    op.create_index(
        "ix_standards_change_candidates_materiality",
        "standards_change_candidates",
        ["materiality"],
    )
    op.create_index(
        "ix_standards_change_candidates_status",
        "standards_change_candidates",
        ["status"],
    )
    op.create_index(
        "ix_standards_change_candidates_created_at",
        "standards_change_candidates",
        ["created_at"],
    )
    op.create_index(
        "ix_standards_change_status_created",
        "standards_change_candidates",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_standards_change_source_created",
        "standards_change_candidates",
        ["source_id", "created_at"],
    )

    op.create_table(
        "standards_impact_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("impact_type", sa.String(length=60), nullable=False),
        sa.Column("impact_key", sa.String(length=160), nullable=False),
        sa.Column("impact_reason", sa.Text(), nullable=False),
        sa.Column("risk_state", sa.String(length=30), nullable=False),
        sa.Column("is_blocking", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["standards_change_candidates.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            "impact_type",
            "impact_key",
            name="uq_standards_impact_candidate_key",
        ),
    )
    op.create_index(
        "ix_standards_impact_links_candidate_id",
        "standards_impact_links",
        ["candidate_id"],
    )
    op.create_index(
        "ix_standards_impact_links_is_blocking",
        "standards_impact_links",
        ["is_blocking"],
    )
    op.create_index(
        "ix_standards_impact_candidate_blocking",
        "standards_impact_links",
        ["candidate_id", "is_blocking"],
    )
    op.create_index(
        "ix_standards_impact_type_key",
        "standards_impact_links",
        ["impact_type", "impact_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_standards_impact_type_key", table_name="standards_impact_links")
    op.drop_index(
        "ix_standards_impact_candidate_blocking",
        table_name="standards_impact_links",
    )
    op.drop_index(
        "ix_standards_impact_links_is_blocking",
        table_name="standards_impact_links",
    )
    op.drop_index(
        "ix_standards_impact_links_candidate_id",
        table_name="standards_impact_links",
    )
    op.drop_table("standards_impact_links")

    op.drop_index(
        "ix_standards_change_source_created",
        table_name="standards_change_candidates",
    )
    op.drop_index(
        "ix_standards_change_status_created",
        table_name="standards_change_candidates",
    )
    op.drop_index(
        "ix_standards_change_candidates_created_at",
        table_name="standards_change_candidates",
    )
    op.drop_index(
        "ix_standards_change_candidates_status",
        table_name="standards_change_candidates",
    )
    op.drop_index(
        "ix_standards_change_candidates_materiality",
        table_name="standards_change_candidates",
    )
    op.drop_index(
        "ix_standards_change_candidates_change_type",
        table_name="standards_change_candidates",
    )
    op.drop_index(
        "ix_standards_change_candidates_current_snapshot_id",
        table_name="standards_change_candidates",
    )
    op.drop_index(
        "ix_standards_change_candidates_source_id",
        table_name="standards_change_candidates",
    )
    op.drop_table("standards_change_candidates")
