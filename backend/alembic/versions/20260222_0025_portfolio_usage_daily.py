"""portfolio usage daily rollup foundation

Revision ID: 20260222_0025
Revises: 20260221_0024
Create Date: 2026-02-22 09:40:00
"""

from __future__ import annotations

from alembic import context
from alembic import op
import sqlalchemy as sa


revision = "20260222_0025"
down_revision = "20260221_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(bind)
    tables = set() if offline else set(inspector.get_table_names())

    if offline or "portfolio_usage_daily" not in tables:
        op.create_table(
            "portfolio_usage_daily",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column(
                "organization_id",
                sa.String(length=36),
                sa.ForeignKey("organizations.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "portfolio_id",
                sa.String(length=36),
                sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("usage_date", sa.Date(), nullable=False),
            sa.Column("provider_calls", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("crawl_pages_fetched", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reports_generated", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("active_campaign_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("portfolio_id", "usage_date", name="uq_portfolio_usage_daily_portfolio_date"),
            sa.CheckConstraint("provider_calls >= 0", name="ck_portfolio_usage_daily_provider_calls_non_negative"),
            sa.CheckConstraint("crawl_pages_fetched >= 0", name="ck_portfolio_usage_daily_crawl_pages_non_negative"),
            sa.CheckConstraint("reports_generated >= 0", name="ck_portfolio_usage_daily_reports_non_negative"),
            sa.CheckConstraint("active_campaign_days >= 0", name="ck_portfolio_usage_daily_active_campaign_days_non_negative"),
        )

    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="portfolio_usage_daily",
        index_name="ix_portfolio_usage_daily_organization_id",
        columns=["organization_id"],
    )
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="portfolio_usage_daily",
        index_name="ix_portfolio_usage_daily_portfolio_id",
        columns=["portfolio_id"],
    )
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="portfolio_usage_daily",
        index_name="ix_portfolio_usage_daily_usage_date",
        columns=["usage_date"],
    )
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="portfolio_usage_daily",
        index_name="ix_portfolio_usage_daily_portfolio_date",
        columns=["portfolio_id", "usage_date"],
    )
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="portfolio_usage_daily",
        index_name="ix_portfolio_usage_daily_org_usage_date",
        columns=["organization_id", "usage_date"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(bind)
    tables = set() if offline else set(inspector.get_table_names())
    if not offline and "portfolio_usage_daily" not in tables:
        return

    _drop_index_if_exists(inspector=inspector, offline=offline, table_name="portfolio_usage_daily", index_name="ix_portfolio_usage_daily_org_usage_date")
    _drop_index_if_exists(inspector=inspector, offline=offline, table_name="portfolio_usage_daily", index_name="ix_portfolio_usage_daily_portfolio_date")
    _drop_index_if_exists(inspector=inspector, offline=offline, table_name="portfolio_usage_daily", index_name="ix_portfolio_usage_daily_usage_date")
    _drop_index_if_exists(inspector=inspector, offline=offline, table_name="portfolio_usage_daily", index_name="ix_portfolio_usage_daily_portfolio_id")
    _drop_index_if_exists(inspector=inspector, offline=offline, table_name="portfolio_usage_daily", index_name="ix_portfolio_usage_daily_organization_id")
    op.drop_table("portfolio_usage_daily")


def _create_index_if_missing(*, inspector: sa.Inspector | None, offline: bool, table_name: str, index_name: str, columns: list[str]) -> None:
    if offline:
        op.create_index(index_name, table_name, columns)
        return

    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in indexes:
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(*, inspector: sa.Inspector | None, offline: bool, table_name: str, index_name: str) -> None:
    if offline:
        op.drop_index(index_name, table_name=table_name)
        return

    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in indexes:
        op.drop_index(index_name, table_name=table_name)
