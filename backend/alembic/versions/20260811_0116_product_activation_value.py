"""add governed product activation and value measurement

Revision ID: 20260811_0116
Revises: 20260811_0115
Create Date: 2026-08-11 16:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260811_0116"
down_revision = "20260811_0115"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_analytics_events",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("campaign_id", sa.String(36), nullable=True),
        sa.Column("event_name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("schema_version", sa.String(20), nullable=False),
        sa.Column("plan_type", sa.String(30), nullable=False),
        sa.Column("source", sa.String(24), nullable=False, server_default="product_client"),
        sa.Column("properties_json", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=True),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_product_analytics_events_org_idempotency",
        ),
    )
    op.create_table(
        "product_feedback",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("campaign_id", sa.String(36), nullable=True),
        sa.Column("context", sa.String(40), nullable=False),
        sa.Column("subject_type", sa.String(40), nullable=False),
        sa.Column("subject_id", sa.String(80), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("plan_type", sa.String(30), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.CheckConstraint("rating >= 1 and rating <= 5", name="ck_product_feedback_rating"),
    )
    event_indexes = (
        "tenant_id",
        "organization_id",
        "actor_user_id",
        "campaign_id",
        "event_name",
        "category",
        "plan_type",
        "is_synthetic",
        "occurred_at",
        "received_at",
    )
    for column in event_indexes:
        op.create_index(
            f"ix_product_analytics_events_{column}", "product_analytics_events", [column]
        )
    op.create_index(
        "ix_product_analytics_events_org_occurred",
        "product_analytics_events",
        ["organization_id", "occurred_at"],
    )
    op.create_index(
        "ix_product_analytics_events_name_occurred",
        "product_analytics_events",
        ["event_name", "occurred_at"],
    )
    feedback_indexes = (
        "tenant_id",
        "organization_id",
        "actor_user_id",
        "campaign_id",
        "context",
        "plan_type",
        "is_synthetic",
        "created_at",
    )
    for column in feedback_indexes:
        op.create_index(f"ix_product_feedback_{column}", "product_feedback", [column])
    op.create_index(
        "ix_product_feedback_context_created",
        "product_feedback",
        ["context", "created_at"],
    )
    op.create_index(
        "ix_product_feedback_org_created",
        "product_feedback",
        ["organization_id", "created_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in ("product_analytics_events", "product_feedback"):
            op.execute(sa.text(f"GRANT SELECT, INSERT ON TABLE public.{table} TO lsos_app"))
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
    op.drop_table("product_feedback")
    op.drop_table("product_analytics_events")
