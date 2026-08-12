"""add evidence-backed competitor discovery fields

Revision ID: 20260812_0125
Revises: 20260812_0124
Create Date: 2026-08-12 20:00:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260812_0125"
down_revision = "20260812_0124"
branch_labels = None
depends_on = None

PRICE_CARD_ID = "f3bda3e5-2c94-49f8-94fd-8cfc0af97215"


def upgrade() -> None:
    with op.batch_alter_table("competitors") as batch_op:
        batch_op.add_column(sa.Column("discovery_source", sa.String(40), nullable=False, server_default="manual"))
        batch_op.add_column(sa.Column("review_status", sa.String(24), nullable=False, server_default="confirmed"))
        batch_op.add_column(sa.Column("overlap_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("average_position", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("estimated_traffic", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("discovery_evidence", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_competitors_review_status", ["review_status"])

    cards = sa.table(
        "provider_price_cards",
        sa.column("id", sa.String),
        sa.column("provider_name", sa.String),
        sa.column("capability", sa.String),
        sa.column("operation", sa.String),
        sa.column("model_name", sa.String),
        sa.column("version", sa.String),
        sa.column("unit", sa.String),
        sa.column("unit_cost", sa.Numeric),
        sa.column("currency", sa.String),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("active", sa.Boolean),
        sa.column("source_url", sa.String),
    )
    op.bulk_insert(
        cards,
        [
            {
                "id": PRICE_CARD_ID,
                "provider_name": "dataforseo",
                "capability": "competitor_research",
                "operation": "competitors_domain_live",
                "model_name": "",
                "version": "competitor-research-2026-08-12-v1",
                "unit": "request",
                "unit_cost": 0.20,
                "currency": "USD",
                "effective_from": datetime(2026, 8, 12, tzinfo=UTC),
                "active": True,
                "source_url": "https://dataforseo.com/pricing/dataforseo-labs/labs-google",
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM provider_price_cards WHERE id = :id").bindparams(id=PRICE_CARD_ID)
    )
    with op.batch_alter_table("competitors") as batch_op:
        batch_op.drop_index("ix_competitors_review_status")
        batch_op.drop_column("last_observed_at")
        batch_op.drop_column("discovery_evidence")
        batch_op.drop_column("estimated_traffic")
        batch_op.drop_column("average_position")
        batch_op.drop_column("overlap_count")
        batch_op.drop_column("review_status")
        batch_op.drop_column("discovery_source")
