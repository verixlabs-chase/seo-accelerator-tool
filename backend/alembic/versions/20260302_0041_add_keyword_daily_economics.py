"""add keyword daily economics"""

from alembic import op
import sqlalchemy as sa


revision = "20260302_0041"
down_revision = "20260302_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "keyword_daily_economics",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("keyword_id", sa.String(length=36), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("search_volume", sa.Integer(), nullable=False),
        sa.Column("cpc", sa.Numeric(10, 2), nullable=False),
        sa.Column("estimated_clicks", sa.Integer(), nullable=False),
        sa.Column("paid_equivalent_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("ctr_model_version", sa.String(length=32), nullable=False),
        sa.Column("deterministic_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["keyword_id"], ["campaign_keywords.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("keyword_id", "metric_date", name="uq_keyword_daily_economics_keyword_date"),
    )
    op.create_index("ix_keyword_daily_economics_campaign_id", "keyword_daily_economics", ["campaign_id"])
    op.create_index("ix_keyword_daily_economics_keyword_id", "keyword_daily_economics", ["keyword_id"])
    op.create_index("ix_keyword_daily_economics_metric_date", "keyword_daily_economics", ["metric_date"])
    op.create_index("ix_keyword_daily_economics_keyword_date", "keyword_daily_economics", ["keyword_id", "metric_date"])


def downgrade() -> None:
    op.drop_index("ix_keyword_daily_economics_keyword_date", table_name="keyword_daily_economics")
    op.drop_index("ix_keyword_daily_economics_metric_date", table_name="keyword_daily_economics")
    op.drop_index("ix_keyword_daily_economics_keyword_id", table_name="keyword_daily_economics")
    op.drop_index("ix_keyword_daily_economics_campaign_id", table_name="keyword_daily_economics")
    op.drop_table("keyword_daily_economics")
