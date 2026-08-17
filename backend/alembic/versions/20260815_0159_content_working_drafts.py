"""add governed content working drafts

Revision ID: 20260815_0159
Revises: 20260815_0158
Create Date: 2026-08-15 23:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260815_0159"
down_revision = "20260815_0158"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("content_briefs") as batch_op:
        batch_op.create_unique_constraint(
            "uq_content_briefs_id_scope",
            ["id", "tenant_id", "organization_id", "campaign_id"],
        )

    op.create_table(
        "content_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("business_location_id", sa.String(length=36), nullable=True),
        sa.Column("content_brief_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="working"),
        sa.Column("title", sa.String(length=320), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("source_brief_hash", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "automatic_publishing_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status = 'working'", name="ck_content_drafts_status"),
        sa.CheckConstraint(
            "automatic_publishing_allowed = false",
            name="ck_content_drafts_no_automatic_publish",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["content_brief_id", "tenant_id", "organization_id", "campaign_id"],
            [
                "content_briefs.id",
                "content_briefs.tenant_id",
                "content_briefs.organization_id",
                "content_briefs.campaign_id",
            ],
            name="fk_content_drafts_brief_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "content_brief_id",
            name="uq_content_drafts_tenant_brief",
        ),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "content_brief_id",
    ):
        op.create_index(f"ix_content_drafts_{column}", "content_drafts", [column])
    op.create_index(
        "ix_content_drafts_campaign_updated",
        "content_drafts",
        ["campaign_id", "updated_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        scope = (
            "current_setting('app.platform_access', true) = 'on' OR ("
            "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
            "organization_id::text = current_setting('app.current_organization_id', true))"
        )
        op.execute(
            sa.text(
                "GRANT SELECT, INSERT, UPDATE ON TABLE public.content_drafts TO lsos_app"
            )
        )
        op.execute(sa.text("REVOKE DELETE ON TABLE public.content_drafts FROM lsos_app"))
        op.execute(sa.text("ALTER TABLE public.content_drafts ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                "CREATE POLICY content_drafts_scope ON public.content_drafts "
                f"FOR ALL TO lsos_app USING ({scope}) WITH CHECK ({scope})"
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text("DROP POLICY IF EXISTS content_drafts_scope ON public.content_drafts")
        )
    op.drop_index("ix_content_drafts_campaign_updated", table_name="content_drafts")
    for column in (
        "content_brief_id",
        "business_location_id",
        "campaign_id",
        "organization_id",
        "tenant_id",
    ):
        op.drop_index(f"ix_content_drafts_{column}", table_name="content_drafts")
    op.drop_table("content_drafts")
    with op.batch_alter_table("content_briefs") as batch_op:
        batch_op.drop_constraint("uq_content_briefs_id_scope", type_="unique")
