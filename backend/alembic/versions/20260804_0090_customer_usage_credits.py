"""add versioned customer usage credits

Revision ID: 20260804_0090
Revises: 20260804_0089
Create Date: 2026-08-04 16:00:00.000000
"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING

from alembic import op
import sqlalchemy as sa


revision = "20260804_0090"
down_revision = "20260804_0089"
branch_labels = None
depends_on = None

CREDIT_POLICY_VERSION = "insight-credits-2026-08-v1"
CREDIT_COST_QUANTUM = Decimal("0.01")


def _drop_append_only_trigger() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            """
            DROP TRIGGER IF EXISTS trg_cost_ledger_append_only
                ON public.cost_ledger_entries;
            """
        )
    )


def _restore_append_only_trigger() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            """
            DROP TRIGGER IF EXISTS trg_cost_ledger_append_only
                ON public.cost_ledger_entries;
            CREATE TRIGGER trg_cost_ledger_append_only
                BEFORE UPDATE OR DELETE ON public.cost_ledger_entries
                FOR EACH ROW
                EXECUTE FUNCTION public.lsos_prevent_cost_ledger_mutation();
            """
        )
    )


def _credits_for_cost(value: object) -> int:
    cost = Decimal(str(value or 0))
    if cost == 0:
        return 0
    magnitude = int((abs(cost) / CREDIT_COST_QUANTUM).to_integral_value(rounding=ROUND_CEILING))
    return magnitude if cost > 0 else -magnitude


def upgrade() -> None:
    with op.batch_alter_table("cost_ledger_entries") as batch_op:
        batch_op.add_column(
            sa.Column(
                "customer_credit_units",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "credit_policy_version",
                sa.String(length=80),
                nullable=False,
                server_default=CREDIT_POLICY_VERSION,
            )
        )

    ledger = sa.table(
        "cost_ledger_entries",
        sa.column("id", sa.String),
        sa.column("credential_owner", sa.String),
        sa.column("event_type", sa.String),
        sa.column("reservation_id", sa.String),
        sa.column("estimated_cost", sa.Numeric),
        sa.column("provider_reported_cost", sa.Numeric),
        sa.column("customer_credit_units", sa.Integer),
        sa.column("credit_policy_version", sa.String),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            ledger.c.id,
            ledger.c.credential_owner,
            ledger.c.event_type,
            ledger.c.reservation_id,
            ledger.c.estimated_cost,
            ledger.c.provider_reported_cost,
        )
    ).all()
    reservation_credits = {
        row.id: _credits_for_cost(row.estimated_cost)
        for row in rows
        if row.credential_owner == "platform" and row.event_type == "reservation"
    }

    # Existing ledger rows need a one-time deterministic backfill. PostgreSQL
    # protects this table with an append-only trigger, so suspend that trigger
    # only inside this transactional migration and restore it immediately after.
    # If any statement fails, PostgreSQL rolls the entire transaction back,
    # including the trigger change.
    _drop_append_only_trigger()
    for row in rows:
        units = 0
        if row.credential_owner == "platform":
            reserved_units = reservation_credits.get(row.reservation_id or row.id, 0)
            if row.event_type == "reservation":
                units = reserved_units
            elif row.event_type == "release":
                units = -reserved_units
            elif row.event_type == "reconciliation":
                actual_units = _credits_for_cost(
                    row.provider_reported_cost
                    if row.provider_reported_cost is not None
                    else row.estimated_cost
                )
                units = actual_units - reserved_units
        connection.execute(
            ledger.update()
            .where(ledger.c.id == row.id)
            .values(
                customer_credit_units=units,
                credit_policy_version=CREDIT_POLICY_VERSION,
            )
        )
    _restore_append_only_trigger()

    with op.batch_alter_table("cost_ledger_entries") as batch_op:
        batch_op.alter_column("customer_credit_units", server_default=None)
        batch_op.alter_column("credit_policy_version", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("cost_ledger_entries") as batch_op:
        batch_op.drop_column("credit_policy_version")
        batch_op.drop_column("customer_credit_units")
