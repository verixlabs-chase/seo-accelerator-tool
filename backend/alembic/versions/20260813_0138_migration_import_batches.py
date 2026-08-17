"""add governed migration import batches

Revision ID: 20260813_0138
Revises: 20260813_0137
Create Date: 2026-08-13 15:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0138"
down_revision = "20260813_0137"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "migration_import_batches",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("source_system", sa.String(30), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=True),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("review_hash", sa.String(64), nullable=False),
        sa.Column("client_request_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("created_entities", sa.JSON(), nullable=False),
        sa.Column("applied_by", sa.String(36), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rolled_back_by", sa.String(36), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "client_request_id",
            name="uq_migration_import_batches_org_request",
        ),
    )
    op.create_index("ix_migration_import_batches_tenant_id", "migration_import_batches", ["tenant_id"])
    op.create_index("ix_migration_import_batches_organization_id", "migration_import_batches", ["organization_id"])
    op.create_index("ix_migration_import_batches_review_hash", "migration_import_batches", ["review_hash"])
    op.create_index("ix_migration_import_batches_status", "migration_import_batches", ["status"])
    op.create_index(
        "ix_migration_import_batches_org_created",
        "migration_import_batches",
        ["organization_id", "created_at"],
    )

    op.create_table(
        "migration_import_records",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("record_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("source_values", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_entities", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["migration_import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_migration_import_records_batch_row"),
    )
    op.create_index("ix_migration_import_records_batch_id", "migration_import_records", ["batch_id"])
    op.create_index("ix_migration_import_records_tenant_id", "migration_import_records", ["tenant_id"])
    op.create_index("ix_migration_import_records_organization_id", "migration_import_records", ["organization_id"])
    op.create_index(
        "ix_migration_import_records_batch_status",
        "migration_import_records",
        ["batch_id", "status"],
    )

    if op.get_bind().dialect.name == "postgresql":
        expression = (
            "current_setting('app.platform_access', true) = 'on' OR ("
            "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
            "organization_id::text = current_setting('app.current_organization_id', true))"
        )
        for table in ("migration_import_batches", "migration_import_records"):
            op.execute(
                sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO lsos_app")
            )
            op.execute(sa.text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
            op.execute(
                sa.text(
                    f"CREATE POLICY lsos_tenant_isolation ON public.{table} FOR ALL TO lsos_app "
                    f"USING ({expression}) WITH CHECK ({expression})"
                )
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in ("migration_import_records", "migration_import_batches"):
            op.execute(sa.text(f"DROP POLICY IF EXISTS lsos_tenant_isolation ON public.{table}"))
            op.execute(sa.text(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY"))
    op.drop_table("migration_import_records")
    op.drop_table("migration_import_batches")
