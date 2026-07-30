"""repair the active Mistral governed-AI price card

Revision ID: 20260730_0081
Revises: 20260730_0080
Create Date: 2026-07-30 15:56:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260730_0081"
down_revision = "20260730_0080"
branch_labels = None
depends_on = None


PRICE_CARD_ID = "a480c5c4-531b-4b5c-b0ba-5679c88b0080"
PRICE_CARD_VERSION = "mistral-small-4-2026-03-v1"


def _price_cards() -> sa.TableClause:
    return sa.table(
        "provider_price_cards",
        sa.column("id", sa.String),
        sa.column("provider_name", sa.String),
        sa.column("capability", sa.String),
        sa.column("operation", sa.String),
        sa.column("model_name", sa.String),
        sa.column("version", sa.String),
        sa.column("unit", sa.String),
        sa.column("unit_cost", sa.Numeric),
        sa.column("input_token_cost_per_million", sa.Numeric),
        sa.column("cached_input_token_cost_per_million", sa.Numeric),
        sa.column("output_token_cost_per_million", sa.Numeric),
        sa.column("currency", sa.String),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("effective_to", sa.DateTime(timezone=True)),
        sa.column("active", sa.Boolean),
        sa.column("source_url", sa.String),
    )


def upgrade() -> None:
    price_cards = _price_cards()
    identity = sa.and_(
        price_cards.c.provider_name == "mistral",
        price_cards.c.capability == "governed_ai",
        price_cards.c.operation == "intelligence_brief",
        price_cards.c.model_name == "mistral-small-2603",
        price_cards.c.version == PRICE_CARD_VERSION,
    )
    bind = op.get_bind()
    existing_id = bind.execute(
        sa.select(price_cards.c.id).where(identity).limit(1)
    ).scalar_one_or_none()
    values = {
        "provider_name": "mistral",
        "capability": "governed_ai",
        "operation": "intelligence_brief",
        "model_name": "mistral-small-2603",
        "version": PRICE_CARD_VERSION,
        "unit": "request",
        "unit_cost": 0,
        "input_token_cost_per_million": 0.15,
        "cached_input_token_cost_per_million": None,
        "output_token_cost_per_million": 0.60,
        "currency": "USD",
        "effective_from": datetime(2026, 3, 16, tzinfo=UTC),
        "effective_to": None,
        "active": True,
        "source_url": (
            "https://docs.mistral.ai/models/model-cards/"
            "mistral-small-4-0-26-03"
        ),
    }
    if existing_id is None:
        bind.execute(price_cards.insert().values(id=PRICE_CARD_ID, **values))
    else:
        bind.execute(price_cards.update().where(identity).values(**values))


def downgrade() -> None:
    price_cards = _price_cards()
    op.get_bind().execute(
        price_cards.delete().where(
            sa.and_(
                price_cards.c.provider_name == "mistral",
                price_cards.c.capability == "governed_ai",
                price_cards.c.operation == "intelligence_brief",
                price_cards.c.model_name == "mistral-small-2603",
                price_cards.c.version == PRICE_CARD_VERSION,
            )
        )
    )
