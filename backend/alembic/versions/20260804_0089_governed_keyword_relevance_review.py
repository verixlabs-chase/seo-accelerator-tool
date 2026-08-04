"""add governed keyword relevance review evidence

Revision ID: 20260804_0089
Revises: 20260804_0088
Create Date: 2026-08-04 14:00:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260804_0089"
down_revision = "20260804_0088"
branch_labels = None
depends_on = None

PRICE_CARD_ID = "a480c5c4-531b-4b5c-b0ba-5679c88b0089"
PRICE_CARD_VERSION = "mistral-small-4-keyword-review-2026-03-v1"


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
    with op.batch_alter_table("keyword_research_suggestions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "ai_review_status",
                sa.String(length=24),
                nullable=False,
                server_default="not_requested",
            )
        )
        batch_op.add_column(sa.Column("ai_relevance_status", sa.String(length=24), nullable=True))
        batch_op.add_column(sa.Column("ai_confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("ai_reason", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("ai_run_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("ai_reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_keyword_research_suggestions_ai_run",
            "governed_ai_runs",
            ["ai_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "ck_keyword_research_suggestions_ai_review_status",
            "ai_review_status in ('not_requested','validated','unavailable','rejected')",
        )
        batch_op.create_check_constraint(
            "ck_keyword_research_suggestions_ai_relevance_status",
            "ai_relevance_status is null or ai_relevance_status in ('relevant','needs_review','unrelated')",
        )
        batch_op.create_index(
            "ix_keyword_research_suggestions_ai_review_status",
            ["ai_review_status"],
        )

    price_cards = _price_cards()
    op.get_bind().execute(
        price_cards.insert().values(
            id=PRICE_CARD_ID,
            provider_name="mistral",
            capability="governed_ai",
            operation="keyword_relevance_review",
            model_name="mistral-small-2603",
            version=PRICE_CARD_VERSION,
            unit="request",
            unit_cost=0,
            input_token_cost_per_million=0.15,
            cached_input_token_cost_per_million=None,
            output_token_cost_per_million=0.60,
            currency="USD",
            effective_from=datetime(2026, 3, 16, tzinfo=UTC),
            effective_to=None,
            active=True,
            source_url=(
                "https://docs.mistral.ai/models/model-cards/"
                "mistral-small-4-0-26-03"
            ),
        )
    )


def downgrade() -> None:
    price_cards = _price_cards()
    op.get_bind().execute(
        price_cards.delete().where(
            sa.and_(
                price_cards.c.provider_name == "mistral",
                price_cards.c.capability == "governed_ai",
                price_cards.c.operation == "keyword_relevance_review",
                price_cards.c.model_name == "mistral-small-2603",
                price_cards.c.version == PRICE_CARD_VERSION,
            )
        )
    )
    with op.batch_alter_table("keyword_research_suggestions") as batch_op:
        batch_op.drop_index("ix_keyword_research_suggestions_ai_review_status")
        batch_op.drop_constraint(
            "ck_keyword_research_suggestions_ai_relevance_status", type_="check"
        )
        batch_op.drop_constraint(
            "ck_keyword_research_suggestions_ai_review_status", type_="check"
        )
        batch_op.drop_constraint(
            "fk_keyword_research_suggestions_ai_run", type_="foreignkey"
        )
        batch_op.drop_column("ai_reviewed_at")
        batch_op.drop_column("ai_run_id")
        batch_op.drop_column("ai_reason")
        batch_op.drop_column("ai_confidence")
        batch_op.drop_column("ai_relevance_status")
        batch_op.drop_column("ai_review_status")
