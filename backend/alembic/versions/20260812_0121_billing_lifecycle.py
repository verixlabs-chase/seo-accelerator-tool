"""add organization billing lifecycle and verified webhook receipt ledger

Revision ID: 20260812_0121
Revises: 20260812_0120
Create Date: 2026-08-12 02:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260812_0121"
down_revision = "20260812_0120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.add_column(sa.Column("stripe_price_id", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("billing_current_period_end", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column(
                "billing_cancel_at_period_end",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(sa.Column("billing_last_event_created_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("billing_last_error_code", sa.String(80), nullable=True))
        batch_op.create_index("ix_organizations_stripe_customer_id", ["stripe_customer_id"])
        batch_op.create_index("ix_organizations_stripe_subscription_id", ["stripe_subscription_id"])

    op.create_table(
        "billing_webhook_events",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("provider_event_id", sa.String(255), nullable=False, unique=True),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("api_version", sa.String(40), nullable=True),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("event_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_id", sa.String(255), nullable=True),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
    )
    for column in ("provider_event_id", "event_type", "organization_id", "status"):
        op.create_index(f"ix_billing_webhook_events_{column}", "billing_webhook_events", [column])
    op.create_index(
        "ix_billing_webhook_events_org_created",
        "billing_webhook_events",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_billing_webhook_events_status_type",
        "billing_webhook_events",
        ["status", "event_type"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.billing_webhook_events TO lsos_app"
            )
        )


def downgrade() -> None:
    op.drop_table("billing_webhook_events")
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.drop_index("ix_organizations_stripe_subscription_id")
        batch_op.drop_index("ix_organizations_stripe_customer_id")
        batch_op.drop_column("billing_last_error_code")
        batch_op.drop_column("billing_last_event_created_at")
        batch_op.drop_column("billing_cancel_at_period_end")
        batch_op.drop_column("billing_current_period_end")
        batch_op.drop_column("stripe_price_id")
