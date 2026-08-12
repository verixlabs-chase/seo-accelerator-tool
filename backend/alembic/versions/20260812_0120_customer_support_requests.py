"""add consented customer support requests and diagnostic bundles

Revision ID: 20260812_0120
Revises: 20260811_0119
Create Date: 2026-08-12 01:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260812_0120"
down_revision = "20260811_0119"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_requests",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("reference_code", sa.String(24), nullable=False, unique=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("campaign_id", sa.String(36), nullable=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("page_path", sa.String(80), nullable=False),
        sa.Column("customer_summary", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(24), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("diagnostic_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("operator_access_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("operator_access_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("diagnostic_bundle", sa.JSON(), nullable=True),
        sa.Column("status_history", sa.JSON(), nullable=False),
        sa.Column("response_target_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
    )
    for column in (
        "reference_code",
        "tenant_id",
        "organization_id",
        "actor_user_id",
        "campaign_id",
        "category",
        "priority",
        "status",
        "created_at",
    ):
        op.create_index(f"ix_support_requests_{column}", "support_requests", [column])
    op.create_index(
        "ix_support_requests_org_status_created",
        "support_requests",
        ["organization_id", "status", "created_at"],
    )
    op.create_index(
        "ix_support_requests_status_target",
        "support_requests",
        ["status", "response_target_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.support_requests TO lsos_app"
            )
        )
        op.execute(sa.text("ALTER TABLE public.support_requests ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                "CREATE POLICY lsos_tenant_isolation ON public.support_requests FOR ALL TO lsos_app "
                "USING (current_setting('app.platform_access', true) = 'on' OR "
                "(tenant_id::text = current_setting('app.current_tenant_id', true) AND "
                "organization_id::text = current_setting('app.current_organization_id', true))) "
                "WITH CHECK (current_setting('app.platform_access', true) = 'on' OR "
                "(tenant_id::text = current_setting('app.current_tenant_id', true) AND "
                "organization_id::text = current_setting('app.current_organization_id', true)))"
            )
        )


def downgrade() -> None:
    op.drop_table("support_requests")
