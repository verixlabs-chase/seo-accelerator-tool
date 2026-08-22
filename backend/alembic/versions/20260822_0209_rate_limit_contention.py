"""allow bounded retries for contended request-rate buckets

Revision ID: 20260822_0209
Revises: 20260821_0208
Create Date: 2026-08-22 16:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260822_0209"
down_revision = "20260821_0208"
branch_labels = None
depends_on = None

CONSUME_SIGNATURE = "public.consume_request_rate_limit(text, text, integer)"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    # A burst of requests for a brand-new bucket serializes briefly on the
    # primary-key index. Keep the wait bounded well inside the middleware's
    # five-second admission deadline while leaving enough room for the store's
    # transaction-level retry to complete on hosted PostgreSQL runners.
    op.execute(
        sa.text(
            f"ALTER FUNCTION {CONSUME_SIGNATURE} "
            "SET statement_timeout = '2s'"
        )
    )
    op.execute(
        sa.text(
            f"ALTER FUNCTION {CONSUME_SIGNATURE} "
            "SET lock_timeout = '750ms'"
        )
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        sa.text(
            f"ALTER FUNCTION {CONSUME_SIGNATURE} "
            "SET statement_timeout = '750ms'"
        )
    )
    op.execute(
        sa.text(
            f"ALTER FUNCTION {CONSUME_SIGNATURE} "
            "SET lock_timeout = '250ms'"
        )
    )
