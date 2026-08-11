"""add governed review request campaigns

Revision ID: 20260810_0111
Revises: 20260810_0110
Create Date: 2026-08-10 23:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260810_0111"
down_revision = "20260810_0110"
branch_labels = None
depends_on = None


def _scope_columns() -> list[sa.Column]:
    return [
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
    ]


def _scope_foreign_keys(prefix: str) -> list[sa.ForeignKeyConstraint]:
    return [
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE", name=f"fk_{prefix}_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name=f"fk_{prefix}_organization",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaigns.id"], ondelete="CASCADE", name=f"fk_{prefix}_campaign"
        ),
        sa.ForeignKeyConstraint(
            ["business_location_id"],
            ["business_locations.id"],
            ondelete="CASCADE",
            name=f"fk_{prefix}_location",
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "reputation_review_request_campaigns",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        *_scope_columns(),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("subject", sa.String(180), nullable=True),
        sa.Column("message_body", sa.Text(), nullable=False),
        sa.Column("review_url", sa.Text(), nullable=False),
        sa.Column("review_url_source", sa.String(32), nullable=False),
        sa.Column("audience_rule", sa.JSON(), nullable=False),
        sa.Column("consent_policy_version", sa.String(80), nullable=False),
        sa.Column("suppression_policy_version", sa.String(80), nullable=False),
        sa.Column("baseline_review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("baseline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *_scope_foreign_keys("review_request_campaign"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "channel in ('email','link','qr','kiosk','sms')",
            name="ck_reputation_review_request_campaign_channel",
        ),
        sa.CheckConstraint(
            "status in ('draft','active','paused','completed','cancelled')",
            name="ck_reputation_review_request_campaign_status",
        ),
        sa.CheckConstraint(
            "review_url_source in ('connected_profile','owner_provided')",
            name="ck_reputation_review_request_campaign_url_source",
        ),
    )
    op.create_table(
        "reputation_review_request_recipients",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        *_scope_columns(),
        sa.Column("request_campaign_id", sa.String(36), nullable=False),
        sa.Column("email_address", sa.String(320), nullable=False),
        sa.Column("contact_hash", sa.String(64), nullable=False),
        sa.Column("customer_name", sa.String(160), nullable=True),
        sa.Column("consent_basis", sa.String(48), nullable=False),
        sa.Column("consent_source", sa.String(160), nullable=False),
        sa.Column("consent_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service_completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="eligible"),
        sa.Column("suppression_reason", sa.String(160), nullable=True),
        sa.Column("suppressed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *_scope_foreign_keys("review_request_recipient"),
        sa.ForeignKeyConstraint(
            ["request_campaign_id"],
            ["reputation_review_request_campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "request_campaign_id",
            "contact_hash",
            name="uq_reputation_review_request_recipient_campaign_contact",
        ),
        sa.CheckConstraint(
            "consent_basis in ('explicit_opt_in','existing_customer_relationship','customer_requested')",
            name="ck_reputation_review_request_recipient_consent_basis",
        ),
        sa.CheckConstraint(
            "status in ('eligible','suppressed','queued','sent','delivered','failed','bounced','complained','unsubscribed')",
            name="ck_reputation_review_request_recipient_status",
        ),
    )
    op.create_table(
        "reputation_review_request_suppressions",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("contact_hash", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(160), nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "channel",
            "contact_hash",
            name="uq_reputation_review_request_suppression_contact",
        ),
        sa.CheckConstraint(
            "channel in ('email','sms')",
            name="ck_reputation_review_request_suppression_channel",
        ),
    )
    op.create_table(
        "reputation_review_request_deliveries",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        *_scope_columns(),
        sa.Column("request_campaign_id", sa.String(36), nullable=False),
        sa.Column("recipient_id", sa.String(36), nullable=False),
        sa.Column("platform_job_id", sa.String(36), nullable=True),
        sa.Column("cost_reservation_id", sa.String(36), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("provider_name", sa.String(80), nullable=True),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("provider_receipt", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *_scope_foreign_keys("review_request_delivery"),
        sa.ForeignKeyConstraint(
            ["request_campaign_id"],
            ["reputation_review_request_campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["reputation_review_request_recipients.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["platform_job_id"], ["platform_jobs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["cost_reservation_id"], ["cost_ledger_entries.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_reputation_review_request_delivery_org_key",
        ),
        sa.CheckConstraint(
            "status in ('queued','sending','sent','delivered','failed','bounced','complained','suppressed','cancelled')",
            name="ck_reputation_review_request_delivery_status",
        ),
    )

    indexes = {
        "reputation_review_request_campaigns": (
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            "channel",
            "status",
            "created_at",
        ),
        "reputation_review_request_recipients": (
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            "request_campaign_id",
            "contact_hash",
            "status",
            "created_at",
        ),
        "reputation_review_request_suppressions": (
            "tenant_id",
            "organization_id",
            "contact_hash",
            "created_at",
        ),
        "reputation_review_request_deliveries": (
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            "request_campaign_id",
            "recipient_id",
            "platform_job_id",
            "status",
            "created_at",
        ),
    }
    for table, columns in indexes.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index(
        "ix_reputation_review_request_campaigns_campaign_status",
        "reputation_review_request_campaigns",
        ["campaign_id", "status"],
    )
    op.create_index(
        "ix_reputation_review_request_recipients_campaign_status",
        "reputation_review_request_recipients",
        ["request_campaign_id", "status"],
    )
    op.create_index(
        "ix_reputation_review_request_suppressions_org_channel",
        "reputation_review_request_suppressions",
        ["organization_id", "channel"],
    )
    op.create_index(
        "ix_reputation_review_request_deliveries_campaign_status",
        "reputation_review_request_deliveries",
        ["request_campaign_id", "status"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in indexes:
            op.execute(
                sa.text(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO lsos_app"
                )
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
    op.drop_table("reputation_review_request_deliveries")
    op.drop_table("reputation_review_request_suppressions")
    op.drop_table("reputation_review_request_recipients")
    op.drop_table("reputation_review_request_campaigns")
