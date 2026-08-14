"""close billing lifecycle idempotency and provider identity gaps

Revision ID: 20260814_0154
Revises: 20260814_0153
Create Date: 2026-08-14 21:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260814_0154"
down_revision = "20260814_0153"
branch_labels = None
depends_on = None


def _assert_unique_external_ids() -> None:
    bind = op.get_bind()
    for column_name in ("stripe_customer_id", "stripe_subscription_id"):
        duplicate = bind.execute(
            sa.text(
                f"""
                SELECT 1
                FROM organizations
                WHERE {column_name} IS NOT NULL
                GROUP BY {column_name}
                HAVING COUNT(*) > 1
                LIMIT 1
                """
            )
        ).first()
        if duplicate is not None:
            raise RuntimeError(
                "Billing provider identity uniqueness preflight failed: "
                f"duplicate non-null {column_name} values must be reviewed without mutation."
            )


def upgrade() -> None:
    _assert_unique_external_ids()
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.add_column(
            sa.Column("billing_last_checkout_request_id", sa.String(128), nullable=True)
        )
        batch_op.add_column(
            sa.Column("billing_last_checkout_session_id", sa.String(255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("billing_last_checkout_plan_code", sa.String(30), nullable=True)
        )
        batch_op.add_column(
            sa.Column("billing_pending_checkout_request_id", sa.String(128), nullable=True)
        )
        batch_op.add_column(
            sa.Column("billing_pending_checkout_session_id", sa.String(255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("billing_pending_checkout_plan_code", sa.String(30), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "billing_pending_checkout_expires_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("billing_subscription_status", sa.String(40), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "billing_subscription_event_created_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("billing_subscription_event_type", sa.String(120), nullable=True)
        )
        batch_op.add_column(
            sa.Column("billing_payment_status", sa.String(40), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "billing_payment_event_created_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("billing_payment_event_type", sa.String(120), nullable=True)
        )
        batch_op.drop_index("ix_organizations_stripe_customer_id")
        batch_op.drop_index("ix_organizations_stripe_subscription_id")
        batch_op.create_index(
            "ix_organizations_stripe_customer_id",
            ["stripe_customer_id"],
            unique=True,
        )
        batch_op.create_index(
            "ix_organizations_stripe_subscription_id",
            ["stripe_subscription_id"],
            unique=True,
        )

    op.execute(
        sa.text(
            """
            UPDATE organizations
            SET billing_subscription_status = billing_status,
                billing_subscription_event_created_at = billing_last_event_created_at,
                billing_subscription_event_type = 'legacy.migrated'
            WHERE billing_status IN ('active', 'trialing', 'canceled', 'unpaid', 'incomplete_expired')
            """
        )
    )
    # Legacy recovery states came from invoice events. A connected subscription was
    # still active unless a terminal subscription event had already changed the row.
    # Preserve that conservative dimension with an explicit inference marker.
    op.execute(
        sa.text(
            """
            UPDATE organizations
            SET billing_subscription_status = 'active',
                billing_subscription_event_created_at = billing_last_event_created_at,
                billing_subscription_event_type = 'legacy.recovery_inferred'
            WHERE billing_status IN ('past_due', 'payment_action_required')
              AND stripe_subscription_id IS NOT NULL
              AND billing_subscription_status IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE organizations
            SET billing_payment_status = billing_status,
                billing_payment_event_created_at = billing_last_event_created_at,
                billing_payment_event_type = 'legacy.migrated'
            WHERE billing_status IN ('past_due', 'payment_action_required')
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.drop_index("ix_organizations_stripe_subscription_id")
        batch_op.drop_index("ix_organizations_stripe_customer_id")
        batch_op.create_index(
            "ix_organizations_stripe_subscription_id",
            ["stripe_subscription_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_organizations_stripe_customer_id",
            ["stripe_customer_id"],
            unique=False,
        )
        batch_op.drop_column("billing_last_checkout_plan_code")
        batch_op.drop_column("billing_last_checkout_session_id")
        batch_op.drop_column("billing_last_checkout_request_id")
        batch_op.drop_column("billing_payment_event_type")
        batch_op.drop_column("billing_payment_event_created_at")
        batch_op.drop_column("billing_payment_status")
        batch_op.drop_column("billing_subscription_event_type")
        batch_op.drop_column("billing_subscription_event_created_at")
        batch_op.drop_column("billing_subscription_status")
        batch_op.drop_column("billing_pending_checkout_expires_at")
        batch_op.drop_column("billing_pending_checkout_plan_code")
        batch_op.drop_column("billing_pending_checkout_session_id")
        batch_op.drop_column("billing_pending_checkout_request_id")
