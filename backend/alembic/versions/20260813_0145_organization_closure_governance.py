"""add governed organization closure records

Revision ID: 20260813_0145
Revises: 20260813_0144
Create Date: 2026-08-13 22:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0145"
down_revision = "20260813_0144"
branch_labels = None
depends_on = None


def _enable_rls(table_name: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    expression = (
        "current_setting('app.platform_access', true) = 'on' OR ("
        "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
        "organization_id::text = current_setting('app.current_organization_id', true))"
    )
    op.execute(
        sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table_name} TO lsos_app")
    )
    op.execute(sa.text(f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY lsos_tenant_isolation ON public.{table_name} "
            f"FOR ALL TO lsos_app USING ({expression}) WITH CHECK ({expression})"
        )
    )


def upgrade() -> None:
    op.create_table(
        "organization_closure_requests",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("client_request_id", sa.String(36), nullable=False),
        sa.Column("requested_by_user_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("hold_status", sa.String(24), nullable=False),
        sa.Column("operational_snapshot", sa.JSON(), nullable=False),
        sa.Column("action_counts", sa.JSON(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recovery_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deletion_ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "client_request_id",
            name="uq_org_closure_requests_org_request",
        ),
    )
    op.create_index("ix_organization_closure_requests_tenant_id", "organization_closure_requests", ["tenant_id"])
    op.create_index("ix_organization_closure_requests_organization_id", "organization_closure_requests", ["organization_id"])
    op.create_index("ix_organization_closure_requests_requested_by_user_id", "organization_closure_requests", ["requested_by_user_id"])
    op.create_index("ix_organization_closure_requests_status", "organization_closure_requests", ["status"])
    op.create_index("ix_organization_closure_requests_recovery_until", "organization_closure_requests", ["recovery_until"])
    op.create_index("ix_org_closure_requests_org_created", "organization_closure_requests", ["organization_id", "created_at"])
    op.create_index("ix_org_closure_requests_due", "organization_closure_requests", ["status", "recovery_until"])

    op.create_table(
        "organization_legal_holds",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("hold_reference", sa.String(160), nullable=False),
        sa.Column("reason_summary", sa.Text(), nullable=False),
        sa.Column("placed_by_user_id", sa.String(36), nullable=True),
        sa.Column("released_by_user_id", sa.String(36), nullable=True),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["placed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["released_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organization_legal_holds_tenant_id", "organization_legal_holds", ["tenant_id"])
    op.create_index("ix_organization_legal_holds_organization_id", "organization_legal_holds", ["organization_id"])
    op.create_index("ix_organization_legal_holds_status", "organization_legal_holds", ["status"])
    op.create_index("ix_organization_legal_holds_placed_by_user_id", "organization_legal_holds", ["placed_by_user_id"])
    op.create_index("ix_organization_legal_holds_released_by_user_id", "organization_legal_holds", ["released_by_user_id"])
    op.create_index("ix_organization_legal_holds_org_status", "organization_legal_holds", ["organization_id", "status"])

    op.create_table(
        "organization_deletion_tombstones",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("closure_request_id", sa.String(36), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("primary_store_status", sa.String(40), nullable=False),
        sa.Column("backup_reapply_required", sa.Boolean(), nullable=False),
        sa.Column("delete_not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("primary_store_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_organization_deletion_tombstones_org"),
    )
    op.create_index("ix_organization_deletion_tombstones_tenant_id", "organization_deletion_tombstones", ["tenant_id"])
    op.create_index("ix_organization_deletion_tombstones_organization_id", "organization_deletion_tombstones", ["organization_id"])
    op.create_index("ix_organization_deletion_tombstones_closure_request_id", "organization_deletion_tombstones", ["closure_request_id"])
    op.create_index("ix_organization_deletion_tombstones_state", "organization_deletion_tombstones", ["state"])

    for table_name in (
        "organization_closure_requests",
        "organization_legal_holds",
        "organization_deletion_tombstones",
    ):
        _enable_rls(table_name)


def downgrade() -> None:
    for table_name in (
        "organization_deletion_tombstones",
        "organization_legal_holds",
        "organization_closure_requests",
    ):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(sa.text(f"DROP POLICY IF EXISTS lsos_tenant_isolation ON public.{table_name}"))
            op.execute(sa.text(f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY"))
        op.drop_table(table_name)
