"""store confirmed competitor positions on local rank grids

Revision ID: 20260812_0126
Revises: 20260812_0125
Create Date: 2026-08-12 21:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260812_0126"
down_revision = "20260812_0125"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("local_rank_grid_runs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "competitor_snapshot",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )

    op.create_table(
        "local_rank_grid_competitor_points",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("point_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
        sa.Column("competitor_id", sa.String(36), nullable=False),
        sa.Column("competitor_domain", sa.String(320), nullable=False),
        sa.Column("competitor_label", sa.String(120), nullable=True),
        sa.Column("keyword_id", sa.String(36), nullable=False),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("grid_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("matched_business_name", sa.String(255), nullable=True),
        sa.Column("matched_business_domain", sa.String(320), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('ranked','not_found')",
            name="ck_local_rank_grid_competitor_points_status",
        ),
        sa.CheckConstraint(
            "rank is null or rank >= 1",
            name="ck_local_rank_grid_competitor_points_rank",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["local_rank_grid_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["point_id"], ["local_rank_grid_points.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["keyword_id"], ["campaign_keywords.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "competitor_id",
            "keyword_id",
            "grid_index",
            name="uq_local_rank_grid_competitor_points_scope",
        ),
    )
    op.create_index(
        "ix_local_rank_grid_competitor_points_run_keyword",
        "local_rank_grid_competitor_points",
        ["run_id", "keyword_id", "competitor_id"],
    )
    for column in (
        "run_id",
        "point_id",
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "competitor_id",
        "keyword_id",
    ):
        op.create_index(
            f"ix_local_rank_grid_competitor_points_{column}",
            "local_rank_grid_competitor_points",
            [column],
        )


def downgrade() -> None:
    op.drop_table("local_rank_grid_competitor_points")
    with op.batch_alter_table("local_rank_grid_runs") as batch_op:
        batch_op.drop_column("competitor_snapshot")
