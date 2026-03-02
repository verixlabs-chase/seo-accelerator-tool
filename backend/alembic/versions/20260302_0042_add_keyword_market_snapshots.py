"""add keyword market snapshots"""

from alembic import op
import sqlalchemy as sa


revision = "20260302_0042"
down_revision = "20260302_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "keyword_market_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("keyword_id", sa.String(length=36), nullable=False),
        sa.Column("search_volume", sa.Integer(), nullable=False),
        sa.Column("avg_cpc", sa.Numeric(10, 2), nullable=False),
        sa.Column("geo_scope", sa.String(length=64), nullable=False),
        sa.Column("device_class", sa.String(length=16), nullable=False),
        sa.Column("source_provider", sa.String(length=64), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("deterministic_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["keyword_id"], ["campaign_keywords.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "keyword_id",
            "geo_scope",
            "device_class",
            "snapshot_date",
            name="uq_keyword_market_snapshots_keyword_geo_device_date",
        ),
    )
    op.create_index("ix_keyword_market_snapshots_keyword_id", "keyword_market_snapshots", ["keyword_id"])
    op.create_index("ix_keyword_market_snapshots_snapshot_date", "keyword_market_snapshots", ["snapshot_date"])
    op.create_index(
        "ix_keyword_market_snapshots_geo_device_date",
        "keyword_market_snapshots",
        ["geo_scope", "device_class", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_keyword_market_snapshots_geo_device_date", table_name="keyword_market_snapshots")
    op.drop_index("ix_keyword_market_snapshots_snapshot_date", table_name="keyword_market_snapshots")
    op.drop_index("ix_keyword_market_snapshots_keyword_id", table_name="keyword_market_snapshots")
    op.drop_table("keyword_market_snapshots")
