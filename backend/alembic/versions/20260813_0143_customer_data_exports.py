"""add governed customer data exports

Revision ID: 20260813_0143
Revises: 20260813_0142
Create Date: 2026-08-13 21:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0143"
down_revision = "20260813_0142"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_export_requests",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("client_request_id", sa.String(36), nullable=False),
        sa.Column("requested_by_user_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("record_counts", sa.JSON(), nullable=False),
        sa.Column("artifact_content", sa.Text(), nullable=True),
        sa.Column("artifact_sha256", sa.String(64), nullable=True),
        sa.Column("artifact_byte_size", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(80), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
            "client_request_id",
            name="uq_data_export_requests_org_request",
        ),
    )
    op.create_index("ix_data_export_requests_tenant_id", "data_export_requests", ["tenant_id"])
    op.create_index(
        "ix_data_export_requests_organization_id",
        "data_export_requests",
        ["organization_id"],
    )
    op.create_index(
        "ix_data_export_requests_requested_by_user_id",
        "data_export_requests",
        ["requested_by_user_id"],
    )
    op.create_index("ix_data_export_requests_status", "data_export_requests", ["status"])
    op.create_index(
        "ix_data_export_requests_expires_at", "data_export_requests", ["expires_at"]
    )
    op.create_index(
        "ix_data_export_requests_org_created",
        "data_export_requests",
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
                "public.data_export_requests TO lsos_app"
            )
        )
        op.execute(sa.text("ALTER TABLE public.data_export_requests ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                "CREATE POLICY lsos_tenant_isolation ON public.data_export_requests "
                f"FOR ALL TO lsos_app USING ({expression}) WITH CHECK ({expression})"
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP POLICY IF EXISTS lsos_tenant_isolation ON public.data_export_requests"
            )
        )
        op.execute(
            sa.text("ALTER TABLE public.data_export_requests DISABLE ROW LEVEL SECURITY")
        )
    op.drop_table("data_export_requests")
