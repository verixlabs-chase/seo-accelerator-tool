"""add objective provider metric contracts and saved measurement scope

Revision ID: 20260809_0102
Revises: 20260809_0101
Create Date: 2026-08-09 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260809_0102"
down_revision = "20260809_0101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_metric_contract_versions",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("contract_id", sa.String(180), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("metric_family", sa.String(100), nullable=False),
        sa.Column("metric_id", sa.String(180), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(60), nullable=False),
        sa.Column("aggregation", sa.String(100), nullable=False),
        sa.Column("direction", sa.String(32), nullable=False),
        sa.Column("collection_status", sa.String(24), nullable=False),
        sa.Column(
            "authoritative_source_id",
            sa.String(120),
            sa.ForeignKey("standards_source_registry.source_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("required_scope_fields", sa.JSON(), nullable=False),
        sa.Column("optional_scope_fields", sa.JSON(), nullable=False),
        sa.Column("comparison_keys", sa.JSON(), nullable=False),
        sa.Column("freshness_days", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "automatic_activation_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "collection_status in ('collected','derived','not_collected')",
            name="ck_provider_metric_contract_versions_collection_status",
        ),
        sa.CheckConstraint(
            "direction in ('higher_is_better','lower_is_better','neutral','configuration')",
            name="ck_provider_metric_contract_versions_direction",
        ),
        sa.UniqueConstraint(
            "contract_id",
            "version",
            name="uq_provider_metric_contract_versions_contract_version",
        ),
    )
    for name, columns in (
        ("ix_provider_metric_contract_versions_contract_id", ["contract_id"]),
        ("ix_provider_metric_contract_versions_provider_name", ["provider_name"]),
        ("ix_provider_metric_contract_versions_metric_family", ["metric_family"]),
        ("ix_provider_metric_contract_versions_metric_id", ["metric_id"]),
        ("ix_provider_metric_contract_versions_authoritative_source_id", ["authoritative_source_id"]),
        ("ix_provider_metric_contract_versions_is_active", ["is_active"]),
        (
            "ix_provider_metric_contract_versions_provider_family_active",
            ["provider_name", "metric_family", "is_active"],
        ),
    ):
        op.create_index(name, "provider_metric_contract_versions", columns)

    _add_columns(
        "search_console_daily_metrics",
        (
            sa.Column("ctr", sa.Float(), nullable=True),
            sa.Column("property_uri", sa.String(500), nullable=False, server_default="unknown"),
            sa.Column("search_type", sa.String(40), nullable=False, server_default="web"),
            sa.Column("dimensions", sa.JSON(), nullable=False, server_default=sa.text("'[\"date\"]'")),
            sa.Column("filters", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("metric_contract_versions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("scope_key", sa.String(64), nullable=False, server_default="legacy"),
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        ),
    )
    op.execute(
        sa.text(
            "UPDATE search_console_daily_metrics SET ctr = "
            "CASE WHEN impressions > 0 THEN (1.0 * clicks / impressions) ELSE NULL END"
        )
    )
    _add_columns(
        "website_performance_measurements",
        (
            sa.Column("metric_contract_versions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("scope_key", sa.String(64), nullable=False, server_default="legacy"),
        ),
    )
    _add_columns(
        "google_business_profile_snapshots",
        (
            sa.Column("metric_contract_id", sa.String(180), nullable=False, server_default="gbp.profile.configuration"),
            sa.Column("metric_contract_version", sa.String(40), nullable=False, server_default="1.0"),
            sa.Column("source_account_id", sa.String(120), nullable=False, server_default="unknown"),
            sa.Column("scope_key", sa.String(64), nullable=False, server_default="legacy"),
        ),
    )
    _add_columns(
        "google_business_profile_daily_metrics",
        (
            sa.Column("metric_contract_id", sa.String(180), nullable=False, server_default="legacy"),
            sa.Column("metric_contract_version", sa.String(40), nullable=False, server_default="1.0"),
            sa.Column("source_account_id", sa.String(120), nullable=False, server_default="unknown"),
            sa.Column("external_resource_id", sa.String(120), nullable=False, server_default="unknown"),
            sa.Column("scope_key", sa.String(64), nullable=False, server_default="legacy"),
        ),
    )
    _add_columns(
        "google_business_profile_search_keywords",
        (
            sa.Column("measurement_kind", sa.String(32), nullable=False, server_default="exact"),
            sa.Column("metric_contract_id", sa.String(180), nullable=False, server_default="gbp.search_terms.monthly_impressions"),
            sa.Column("metric_contract_version", sa.String(40), nullable=False, server_default="1.0"),
            sa.Column("source_account_id", sa.String(120), nullable=False, server_default="unknown"),
            sa.Column("external_resource_id", sa.String(120), nullable=False, server_default="unknown"),
            sa.Column("scope_key", sa.String(64), nullable=False, server_default="legacy"),
        ),
    )
    _add_columns(
        "local_rank_grid_runs",
        (
            sa.Column("metric_contract_id", sa.String(180), nullable=False, server_default="local_grid.position"),
            sa.Column("metric_contract_version", sa.String(40), nullable=False, server_default="1.0"),
            sa.Column("grid_definition_hash", sa.String(64), nullable=False, server_default="legacy"),
            sa.Column("language_code", sa.String(16), nullable=False, server_default="en"),
            sa.Column("device_class", sa.String(20), nullable=False, server_default="provider_default"),
            sa.Column("provider_method", sa.String(80), nullable=False, server_default="maps_search"),
        ),
    )
    _add_columns(
        "local_rank_grid_points",
        (
            sa.Column("metric_contract_id", sa.String(180), nullable=False, server_default="local_grid.position"),
            sa.Column("metric_contract_version", sa.String(40), nullable=False, server_default="1.0"),
            sa.Column("scope_key", sa.String(64), nullable=False, server_default="legacy"),
        ),
    )
    _add_columns(
        "review_velocity_snapshots",
        (
            sa.Column("metric_contract_versions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("scope_key", sa.String(64), nullable=False, server_default="legacy"),
        ),
    )


def downgrade() -> None:
    _drop_columns("review_velocity_snapshots", ("scope_key", "metric_contract_versions"))
    _drop_columns("local_rank_grid_points", ("scope_key", "metric_contract_version", "metric_contract_id"))
    _drop_columns(
        "local_rank_grid_runs",
        (
            "provider_method",
            "device_class",
            "language_code",
            "grid_definition_hash",
            "metric_contract_version",
            "metric_contract_id",
        ),
    )
    _drop_columns(
        "google_business_profile_search_keywords",
        (
            "scope_key",
            "external_resource_id",
            "source_account_id",
            "metric_contract_version",
            "metric_contract_id",
            "measurement_kind",
        ),
    )
    _drop_columns(
        "google_business_profile_daily_metrics",
        ("scope_key", "external_resource_id", "source_account_id", "metric_contract_version", "metric_contract_id"),
    )
    _drop_columns(
        "google_business_profile_snapshots",
        ("scope_key", "source_account_id", "metric_contract_version", "metric_contract_id"),
    )
    _drop_columns("website_performance_measurements", ("scope_key", "metric_contract_versions"))
    _drop_columns(
        "search_console_daily_metrics",
        (
            "captured_at",
            "scope_key",
            "metric_contract_versions",
            "filters",
            "dimensions",
            "search_type",
            "property_uri",
            "ctr",
        ),
    )
    op.drop_table("provider_metric_contract_versions")


def _add_columns(table_name: str, columns: tuple[sa.Column, ...]) -> None:
    for column in columns:
        op.add_column(table_name, column)


def _drop_columns(table_name: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.drop_column(table_name, column)
