"""add resumable migration upload sessions

Revision ID: 20260813_0142
Revises: 20260813_0141
Create Date: 2026-08-13 20:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0142"
down_revision = "20260813_0141"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "migration_upload_sessions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("client_request_id", sa.String(36), nullable=False),
        sa.Column("source_system", sa.String(30), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=True),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column("expected_sha256", sa.String(64), nullable=True),
        sa.Column("source_sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("received_chunks", sa.Integer(), nullable=False),
        sa.Column("review_hash", sa.String(64), nullable=True),
        sa.Column("review_payload", sa.JSON(), nullable=True),
        sa.Column("applied_batch_id", sa.String(36), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["applied_batch_id"], ["migration_import_batches.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "client_request_id",
            name="uq_migration_upload_sessions_org_request",
        ),
    )
    op.create_index(
        "ix_migration_upload_sessions_tenant_id", "migration_upload_sessions", ["tenant_id"]
    )
    op.create_index(
        "ix_migration_upload_sessions_organization_id",
        "migration_upload_sessions",
        ["organization_id"],
    )
    op.create_index(
        "ix_migration_upload_sessions_status", "migration_upload_sessions", ["status"]
    )
    op.create_index(
        "ix_migration_upload_sessions_applied_batch_id",
        "migration_upload_sessions",
        ["applied_batch_id"],
    )
    op.create_index(
        "ix_migration_upload_sessions_org_updated",
        "migration_upload_sessions",
        ["organization_id", "updated_at"],
    )

    op.create_table(
        "migration_upload_chunks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["migration_upload_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "chunk_index", name="uq_migration_upload_chunks_session_index"
        ),
    )
    op.create_index(
        "ix_migration_upload_chunks_session_id", "migration_upload_chunks", ["session_id"]
    )
    op.create_index(
        "ix_migration_upload_chunks_tenant_id", "migration_upload_chunks", ["tenant_id"]
    )
    op.create_index(
        "ix_migration_upload_chunks_organization_id",
        "migration_upload_chunks",
        ["organization_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        expression = (
            "current_setting('app.platform_access', true) = 'on' OR ("
            "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
            "organization_id::text = current_setting('app.current_organization_id', true))"
        )
        for table in ("migration_upload_sessions", "migration_upload_chunks"):
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
        for table in ("migration_upload_chunks", "migration_upload_sessions"):
            op.execute(sa.text(f"DROP POLICY IF EXISTS lsos_tenant_isolation ON public.{table}"))
            op.execute(sa.text(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY"))
    op.drop_table("migration_upload_chunks")
    op.drop_table("migration_upload_sessions")
