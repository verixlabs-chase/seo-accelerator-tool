"""add location-scoped directory listing inventory

Revision ID: 20260810_0106
Revises: 20260810_0105
Create Date: 2026-08-10 14:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260810_0106"
down_revision = "20260810_0105"
branch_labels = None
depends_on = None


def _scope_columns() -> list[sa.Column]:
    return [
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
    ]


def _scope_foreign_keys(table_name: str) -> list[sa.ForeignKeyConstraint]:
    prefix = "dir_listings" if table_name == "directory_listings" else "dir_listing_obs"
    return [
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE", name=f"fk_{prefix}_tenant_id"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name=f"fk_{prefix}_organization_id",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaigns.id"], ondelete="CASCADE", name=f"fk_{prefix}_campaign_id"
        ),
        sa.ForeignKeyConstraint(
            ["business_location_id"],
            ["business_locations.id"],
            ondelete="CASCADE",
            name=f"fk_{prefix}_business_location_id",
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "directory_listings",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        *_scope_columns(),
        sa.Column("source_key", sa.String(100), nullable=False),
        sa.Column("source_name", sa.String(160), nullable=False),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("listing_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="live"),
        sa.Column("business_name", sa.String(255), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("region", sa.String(120), nullable=True),
        sa.Column("postal_code", sa.String(32), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("website_url", sa.Text(), nullable=True),
        sa.Column("primary_category", sa.String(160), nullable=True),
        sa.Column("observed_fields", sa.JSON(), nullable=False),
        sa.Column("field_differences", sa.JSON(), nullable=False),
        sa.Column("directory_importance", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *_scope_foreign_keys("directory_listings"),
        sa.CheckConstraint(
            "status in ('correct','inconsistent','missing','duplicate','submitted','live','verified','unavailable')",
            name="ck_directory_listings_status",
        ),
        sa.CheckConstraint(
            "directory_importance in ('essential','important','standard','unknown')",
            name="ck_directory_listings_importance",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "business_location_id",
            "source_key",
            "external_id",
            name="uq_directory_listings_location_source_external",
        ),
    )
    op.create_table(
        "directory_listing_observations",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        *_scope_columns(),
        sa.Column("listing_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("observed_fields", sa.JSON(), nullable=False),
        sa.Column("field_differences", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        *_scope_foreign_keys("directory_listing_observations"),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["directory_listings.id"],
            ondelete="CASCADE",
            name="fk_dir_listing_obs_listing_id",
        ),
        sa.UniqueConstraint(
            "listing_id",
            "evidence_digest",
            name="uq_dir_listing_obs_listing_digest",
        ),
    )

    for column in ("tenant_id", "organization_id", "campaign_id", "business_location_id", "status"):
        op.create_index(f"ix_directory_listings_{column}", "directory_listings", [column])
    op.create_index(
        "ix_directory_listings_location_status",
        "directory_listings",
        ["business_location_id", "status"],
    )
    op.create_index("ix_directory_listings_last_seen_at", "directory_listings", ["last_seen_at"])
    for column in ("tenant_id", "organization_id", "campaign_id", "business_location_id", "listing_id"):
        op.create_index(f"ix_dir_listing_obs_{column}", "directory_listing_observations", [column])
    op.create_index("ix_dir_listing_obs_observed_at", "directory_listing_observations", ["observed_at"])
    op.create_index(
        "ix_dir_listing_obs_listing_observed",
        "directory_listing_observations",
        ["listing_id", "observed_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in ("directory_listings", "directory_listing_observations"):
            op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO lsos_app"))
            op.execute(sa.text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
            op.execute(
                sa.text(
                    f"CREATE POLICY lsos_tenant_isolation ON public.{table} FOR ALL TO lsos_app "
                    "USING (current_setting('app.platform_access', true) = 'on' OR "
                    "(tenant_id::text = current_setting('app.current_tenant_id', true) AND "
                    "organization_id::text = current_setting('app.current_organization_id', true))) "
                    "WITH CHECK (current_setting('app.platform_access', true) = 'on' OR "
                    "(tenant_id::text = current_setting('app.current_tenant_id', true) AND "
                    "organization_id::text = current_setting('app.current_organization_id', true)))"
                )
            )


def downgrade() -> None:
    op.drop_table("directory_listing_observations")
    op.drop_table("directory_listings")
