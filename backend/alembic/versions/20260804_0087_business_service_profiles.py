"""add business service profiles and keyword relevance evidence

Revision ID: 20260804_0087
Revises: 20260803_0086
Create Date: 2026-08-04 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260804_0087"
down_revision = "20260803_0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_services",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("business_location_id", sa.String(length=36), nullable=True),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_key", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("normalized_name", sa.String(length=160), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("canonical_category", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope_type in ('organization','location')",
            name="ck_business_services_scope_type",
        ),
        sa.CheckConstraint(
            "status in ('suggested','confirmed','rejected')",
            name="ck_business_services_status",
        ),
        sa.CheckConstraint(
            "source in ('manual','website','business_profile','inherited')",
            name="ck_business_services_source",
        ),
        sa.CheckConstraint(
            "confidence between 0 and 1",
            name="ck_business_services_confidence",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "scope_type",
            "scope_key",
            "normalized_name",
            name="uq_business_services_scope_name",
        ),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "business_location_id",
        "status",
    ):
        op.create_index(f"ix_business_services_{column}", "business_services", [column])
    op.create_index(
        "ix_business_services_location_status",
        "business_services",
        ["business_location_id", "status"],
    )

    with op.batch_alter_table("keyword_research_suggestions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "relevance_status",
                sa.String(length=24),
                nullable=False,
                server_default="needs_review",
            )
        )
        batch_op.add_column(sa.Column("matched_service_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("matched_service_name", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("relevance_reason", sa.String(length=500), nullable=True))
        batch_op.create_foreign_key(
            "fk_keyword_research_suggestions_matched_service",
            "business_services",
            ["matched_service_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "ck_keyword_research_suggestions_relevance_status",
            "relevance_status in ('relevant','needs_review','unrelated')",
        )
        batch_op.create_index(
            "ix_keyword_research_suggestions_relevance_status",
            ["relevance_status"],
        )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON TABLE public.business_services TO lsos_app;

                ALTER TABLE public.business_services ENABLE ROW LEVEL SECURITY;

                CREATE POLICY lsos_tenant_isolation ON public.business_services
                    FOR ALL TO lsos_app
                    USING (
                        current_setting('app.platform_access', true) = 'on'
                        OR (
                            tenant_id::text = current_setting('app.current_tenant_id', true)
                            AND organization_id::text = current_setting('app.current_organization_id', true)
                        )
                    )
                    WITH CHECK (
                        current_setting('app.platform_access', true) = 'on'
                        OR (
                            tenant_id::text = current_setting('app.current_tenant_id', true)
                            AND organization_id::text = current_setting('app.current_organization_id', true)
                        )
                    );
                """
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("keyword_research_suggestions") as batch_op:
        batch_op.drop_index("ix_keyword_research_suggestions_relevance_status")
        batch_op.drop_constraint(
            "ck_keyword_research_suggestions_relevance_status", type_="check"
        )
        batch_op.drop_constraint(
            "fk_keyword_research_suggestions_matched_service", type_="foreignkey"
        )
        batch_op.drop_column("relevance_reason")
        batch_op.drop_column("matched_service_name")
        batch_op.drop_column("matched_service_id")
        batch_op.drop_column("relevance_status")

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP POLICY IF EXISTS lsos_tenant_isolation ON public.business_services"
            )
        )
    op.drop_index("ix_business_services_location_status", table_name="business_services")
    for column in ("status", "business_location_id", "organization_id", "tenant_id"):
        op.drop_index(f"ix_business_services_{column}", table_name="business_services")
    op.drop_table("business_services")
