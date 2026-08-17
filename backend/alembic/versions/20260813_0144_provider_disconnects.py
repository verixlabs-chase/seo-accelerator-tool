"""add governed provider disconnect records

Revision ID: 20260813_0144
Revises: 20260813_0143
Create Date: 2026-08-13 22:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0144"
down_revision = "20260813_0143"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_disconnect_requests",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("provider_name", sa.String(80), nullable=False),
        sa.Column("client_request_id", sa.String(36), nullable=False),
        sa.Column("requested_by_user_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("credential_deleted", sa.Boolean(), nullable=False),
        sa.Column("external_revocation_status", sa.String(40), nullable=False),
        sa.Column("external_revocation_code", sa.String(80), nullable=True),
        sa.Column("connections_disconnected", sa.Integer(), nullable=False),
        sa.Column("queued_jobs_cancelled", sa.Integer(), nullable=False),
        sa.Column("preserved_record_counts", sa.JSON(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider_name",
            "client_request_id",
            name="uq_provider_disconnect_org_provider_request",
        ),
    )
    op.create_index(
        "ix_provider_disconnect_requests_tenant_id",
        "provider_disconnect_requests",
        ["tenant_id"],
    )
    op.create_index(
        "ix_provider_disconnect_requests_organization_id",
        "provider_disconnect_requests",
        ["organization_id"],
    )
    op.create_index(
        "ix_provider_disconnect_requests_provider_name",
        "provider_disconnect_requests",
        ["provider_name"],
    )
    op.create_index(
        "ix_provider_disconnect_requests_requested_by_user_id",
        "provider_disconnect_requests",
        ["requested_by_user_id"],
    )
    op.create_index(
        "ix_provider_disconnect_requests_status",
        "provider_disconnect_requests",
        ["status"],
    )
    op.create_index(
        "ix_provider_disconnect_org_created",
        "provider_disconnect_requests",
        ["organization_id", "created_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        expression = (
            "current_setting('app.platform_access', true) = 'on' OR ("
            "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
            "organization_id::text = current_setting('app.current_organization_id', true))"
        )
        op.execute(
            sa.text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
                "public.provider_disconnect_requests TO lsos_app"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE public.provider_disconnect_requests "
                "ENABLE ROW LEVEL SECURITY"
            )
        )
        op.execute(
            sa.text(
                "CREATE POLICY lsos_tenant_isolation ON public.provider_disconnect_requests "
                f"FOR ALL TO lsos_app USING ({expression}) WITH CHECK ({expression})"
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP POLICY IF EXISTS lsos_tenant_isolation "
                "ON public.provider_disconnect_requests"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE public.provider_disconnect_requests "
                "DISABLE ROW LEVEL SECURITY"
            )
        )
    op.drop_table("provider_disconnect_requests")
