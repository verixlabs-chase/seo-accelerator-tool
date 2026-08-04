"""add location service areas and keyword geography evidence

Revision ID: 20260804_0088
Revises: 20260804_0087
Create Date: 2026-08-04 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260804_0088"
down_revision = "20260804_0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_service_areas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("business_location_id", sa.String(length=36), nullable=False),
        sa.Column("area_type", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("normalized_name", sa.String(length=160), nullable=False),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("radius_miles", sa.Float(), nullable=True),
        sa.Column("center_latitude", sa.Float(), nullable=True),
        sa.Column("center_longitude", sa.Float(), nullable=True),
        sa.Column("relationship", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "area_type in ('city','postal_code','county','radius')",
            name="ck_business_service_areas_type",
        ),
        sa.CheckConstraint(
            "relationship in ('included','excluded')",
            name="ck_business_service_areas_relationship",
        ),
        sa.CheckConstraint(
            "status in ('suggested','confirmed','rejected')",
            name="ck_business_service_areas_status",
        ),
        sa.CheckConstraint(
            "source in ('manual','website','location','business_profile')",
            name="ck_business_service_areas_source",
        ),
        sa.CheckConstraint(
            "confidence between 0 and 1",
            name="ck_business_service_areas_confidence",
        ),
        sa.CheckConstraint(
            "(area_type = 'radius' and radius_miles > 0) or (area_type <> 'radius' and radius_miles is null)",
            name="ck_business_service_areas_radius",
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
            "business_location_id",
            "area_type",
            "normalized_name",
            "relationship",
            name="uq_business_service_areas_location_area",
        ),
    )
    for column in ("tenant_id", "organization_id", "business_location_id", "status"):
        op.create_index(
            f"ix_business_service_areas_{column}", "business_service_areas", [column]
        )
    op.create_index(
        "ix_business_service_areas_location_status",
        "business_service_areas",
        ["business_location_id", "status"],
    )

    with op.batch_alter_table("keyword_research_suggestions") as batch_op:
        batch_op.add_column(
            sa.Column("matched_service_area_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("matched_service_area_name", sa.String(length=160), nullable=True)
        )
        batch_op.add_column(
            sa.Column("area_match_type", sa.String(length=24), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_keyword_research_suggestions_matched_service_area",
            "business_service_areas",
            ["matched_service_area_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON TABLE public.business_service_areas TO lsos_app;

                ALTER TABLE public.business_service_areas ENABLE ROW LEVEL SECURITY;

                CREATE POLICY lsos_tenant_isolation ON public.business_service_areas
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
        batch_op.drop_constraint(
            "fk_keyword_research_suggestions_matched_service_area", type_="foreignkey"
        )
        batch_op.drop_column("area_match_type")
        batch_op.drop_column("matched_service_area_name")
        batch_op.drop_column("matched_service_area_id")

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP POLICY IF EXISTS lsos_tenant_isolation ON public.business_service_areas"
            )
        )
    op.drop_index(
        "ix_business_service_areas_location_status", table_name="business_service_areas"
    )
    for column in ("status", "business_location_id", "organization_id", "tenant_id"):
        op.drop_index(
            f"ix_business_service_areas_{column}", table_name="business_service_areas"
        )
    op.drop_table("business_service_areas")
