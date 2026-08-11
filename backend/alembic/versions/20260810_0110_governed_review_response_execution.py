"""add governed review response execution

Revision ID: 20260810_0110
Revises: 20260810_0109
Create Date: 2026-08-10 21:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260810_0110"
down_revision = "20260810_0109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reputation_provider_capabilities",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("provider_name", sa.String(80), nullable=False),
        sa.Column("capability", sa.String(80), nullable=False),
        sa.Column("provider_method", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("proof_type", sa.String(80), nullable=False),
        sa.Column("proof_reference", sa.Text(), nullable=False),
        sa.Column("authorized_by_user_id", sa.String(36), nullable=True),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_code", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["data_connections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["authorized_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "connection_id",
            "capability",
            name="uq_reputation_provider_capabilities_connection_capability",
        ),
        sa.CheckConstraint(
            "status in ('validation_authorized','verified','revoked')",
            name="ck_reputation_provider_capabilities_status",
        ),
    )
    op.create_table(
        "reputation_response_executions",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
        sa.Column("review_id", sa.String(36), nullable=False),
        sa.Column("draft_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("capability_id", sa.String(36), nullable=False),
        sa.Column("platform_job_id", sa.String(36), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("approved_text", sa.Text(), nullable=False),
        sa.Column("approved_text_hash", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("approval_snapshot", sa.JSON(), nullable=False),
        sa.Column("review_snapshot", sa.JSON(), nullable=False),
        sa.Column("capability_snapshot", sa.JSON(), nullable=False),
        sa.Column("confirmation_version", sa.String(80), nullable=False),
        sa.Column("confirmation_hash", sa.String(64), nullable=False),
        sa.Column("provider_name", sa.String(80), nullable=False),
        sa.Column("provider_method", sa.String(160), nullable=False),
        sa.Column("external_review_resource_name", sa.Text(), nullable=False),
        sa.Column("provider_reply_state", sa.String(40), nullable=True),
        sa.Column("provider_policy_violation", sa.String(120), nullable=True),
        sa.Column("provider_receipt", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", sa.String(36), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["review_id"], ["reputation_reviews.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["draft_id"], ["reputation_response_drafts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["data_connections.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["capability_id"],
            ["reputation_provider_capabilities.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["platform_job_id"], ["platform_jobs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_reputation_response_executions_org_idempotency",
        ),
        sa.UniqueConstraint("draft_id", name="uq_reputation_response_executions_draft"),
        sa.CheckConstraint(
            "status in ('queued','posting','retrying','posted','paused','blocked','failed','cancelled')",
            name="ck_reputation_response_executions_status",
        ),
    )

    indexes = {
        "reputation_provider_capabilities": (
            "tenant_id",
            "organization_id",
            "connection_id",
            "status",
        ),
        "reputation_response_executions": (
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            "review_id",
            "connection_id",
            "capability_id",
            "platform_job_id",
            "status",
            "created_at",
        ),
    }
    for table, columns in indexes.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index(
        "ix_reputation_provider_capabilities_org_status",
        "reputation_provider_capabilities",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_reputation_response_executions_campaign_status",
        "reputation_response_executions",
        ["campaign_id", "status"],
    )
    op.create_index(
        "ix_reputation_response_executions_review_created",
        "reputation_response_executions",
        ["review_id", "created_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "reputation_provider_capabilities",
            "reputation_response_executions",
        ):
            op.execute(
                sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO lsos_app")
            )
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
    op.drop_table("reputation_response_executions")
    op.drop_table("reputation_provider_capabilities")
