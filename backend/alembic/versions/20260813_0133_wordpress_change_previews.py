"""add immutable WordPress change previews

Revision ID: 20260813_0133
Revises: 20260813_0132
Create Date: 2026-08-13 00:02:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0133"
down_revision = "20260813_0132"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wordpress_change_previews",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("execution_id", sa.String(36), nullable=False),
        sa.Column("recommendation_id", sa.String(36), nullable=False),
        sa.Column("preview_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("affected_url_count", sa.Integer(), nullable=False),
        sa.Column("mutation_count", sa.Integer(), nullable=False),
        sa.Column("conflict_count", sa.Integer(), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("approved_by", sa.String(120), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('ready','blocked','approved','superseded')",
            name="ck_wordpress_change_previews_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["recommendation_executions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"], ["strategy_recommendations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "execution_id",
            "preview_hash",
            name="uq_wordpress_change_previews_execution_hash",
        ),
    )
    for column in (
        "tenant_id",
        "campaign_id",
        "execution_id",
        "recommendation_id",
        "preview_hash",
        "status",
        "created_at",
    ):
        op.create_index(
            f"ix_wordpress_change_previews_{column}",
            "wordpress_change_previews",
            [column],
        )
    op.create_index(
        "ix_wordpress_change_previews_execution_created",
        "wordpress_change_previews",
        ["execution_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("wordpress_change_previews")
