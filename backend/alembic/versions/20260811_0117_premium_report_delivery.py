"""add premium report delivery and secure sharing

Revision ID: 20260811_0117
Revises: 20260811_0116
Create Date: 2026-08-11 18:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260811_0117"
down_revision = "20260811_0116"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("report_artifacts") as batch:
        batch.add_column(
            sa.Column(
                "storage_mode",
                sa.String(40),
                nullable=False,
                server_default="local_disk",
            )
        )
        batch.add_column(sa.Column("storage_key", sa.Text(), nullable=True))
        batch.add_column(sa.Column("content_type", sa.String(120), nullable=True))
        batch.add_column(sa.Column("byte_size", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("checksum_sha256", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column("durable", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column("ready", sa.Boolean(), nullable=False, server_default=sa.true())
        )

    with op.batch_alter_table("report_delivery_events") as batch:
        batch.add_column(sa.Column("provider_message_id", sa.String(255), nullable=True))
        batch.add_column(
            sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("failure_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "report_recipients",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=True),
        sa.Column("recipient_role", sa.String(40), nullable=False, server_default="owner"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "campaign_id", "email", name="uq_report_recipients_campaign_email"
        ),
    )
    for column in ("tenant_id", "organization_id", "campaign_id"):
        op.create_index(f"ix_report_recipients_{column}", "report_recipients", [column])
    op.create_index(
        "ix_report_recipients_org_campaign_enabled",
        "report_recipients",
        ["organization_id", "campaign_id", "enabled"],
    )

    op.create_table(
        "report_share_links",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("report_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["report_id"], ["monthly_reports.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("token_hash", name="uq_report_share_links_token_hash"),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "report_id",
        "token_hash",
        "expires_at",
    ):
        op.create_index(f"ix_report_share_links_{column}", "report_share_links", [column])
    op.create_index(
        "ix_report_share_links_org_report_expires",
        "report_share_links",
        ["organization_id", "report_id", "expires_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in ("report_recipients", "report_share_links"):
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
    op.drop_table("report_share_links")
    op.drop_table("report_recipients")
    with op.batch_alter_table("report_delivery_events") as batch:
        batch.drop_column("failed_at")
        batch.drop_column("opened_at")
        batch.drop_column("delivered_at")
        batch.drop_column("failure_reason")
        batch.drop_column("attempt_number")
        batch.drop_column("provider_message_id")
    with op.batch_alter_table("report_artifacts") as batch:
        batch.drop_column("ready")
        batch.drop_column("durable")
        batch.drop_column("checksum_sha256")
        batch.drop_column("byte_size")
        batch.drop_column("content_type")
        batch.drop_column("storage_key")
        batch.drop_column("storage_mode")
