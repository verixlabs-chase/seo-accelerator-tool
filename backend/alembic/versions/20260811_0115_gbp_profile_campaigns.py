"""add approval-gated Google Business Profile campaigns

Revision ID: 20260811_0115
Revises: 20260811_0114
Create Date: 2026-08-11 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260811_0115"
down_revision = "20260811_0114"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_business_profile_campaigns",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("target_snapshot_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("request_key", sa.String(120), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("payload_template_json", sa.JSON(), nullable=False),
        sa.Column("target_hash", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("approval_hash", sa.String(64), nullable=True),
        sa.Column("preflight_json", sa.JSON(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ready_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("approved_by_user_id", sa.String(36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["target_snapshot_id"], ["portfolio_target_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "organization_id", "request_key", name="uq_gbp_campaigns_org_request_key"
        ),
        sa.CheckConstraint(
            "action_type in ('local_post','photo_upload')",
            name="ck_gbp_campaigns_action_type",
        ),
        sa.CheckConstraint(
            "status in ('draft','awaiting_approval','blocked','approved_hold','cancelled')",
            name="ck_gbp_campaigns_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_gbp_campaigns_version"),
        sa.CheckConstraint(
            "ready_count >= 0 and blocked_count >= 0",
            name="ck_gbp_campaigns_nonnegative_counts",
        ),
    )
    op.create_table(
        "google_business_profile_campaign_variants",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("profile_campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=True),
        sa.Column("connection_id", sa.String(36), nullable=True),
        sa.Column("external_resource_id", sa.String(120), nullable=True),
        sa.Column("location_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="blocked"),
        sa.Column("rendered_payload_json", sa.JSON(), nullable=False),
        sa.Column("checks_json", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=True),
        sa.Column("reason_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["profile_campaign_id"],
            ["google_business_profile_campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["data_connections.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "profile_campaign_id",
            "business_location_id",
            name="uq_gbp_campaign_variants_campaign_location",
        ),
        sa.CheckConstraint(
            "status in ('ready','blocked')", name="ck_gbp_campaign_variants_status"
        ),
    )

    indexes = {
        "google_business_profile_campaigns": (
            "tenant_id",
            "organization_id",
            "target_snapshot_id",
            "target_hash",
            "content_hash",
            "approval_hash",
        ),
        "google_business_profile_campaign_variants": (
            "tenant_id",
            "organization_id",
            "profile_campaign_id",
            "business_location_id",
            "campaign_id",
            "connection_id",
            "payload_hash",
        ),
    }
    for table, columns in indexes.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index(
        "ix_gbp_campaigns_org_created",
        "google_business_profile_campaigns",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_gbp_campaigns_org_status",
        "google_business_profile_campaigns",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_gbp_campaign_variants_campaign_status",
        "google_business_profile_campaign_variants",
        ["profile_campaign_id", "status"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "google_business_profile_campaigns",
            "google_business_profile_campaign_variants",
        ):
            op.execute(
                sa.text(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO lsos_app"
                )
            )
            _create_full_access_policy(table)


def _create_full_access_policy(table: str) -> None:
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
    op.drop_table("google_business_profile_campaign_variants")
    op.drop_table("google_business_profile_campaigns")
