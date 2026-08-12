"""add deterministic engagement achievements and preferences

Revision ID: 20260812_0122
Revises: 20260812_0121
Create Date: 2026-08-12 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260812_0122"
down_revision = "20260812_0121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "achievement_grants",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=True),
        sa.Column("rule_key", sa.String(120), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("scope_type", sa.String(24), nullable=False),
        sa.Column("scope_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("qualified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("earned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category in ('foundation','habit','verified_result','multi_location')",
            name="ck_achievement_grants_category",
        ),
        sa.CheckConstraint(
            "scope_type in ('location','organization')",
            name="ck_achievement_grants_scope_type",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "rule_key",
            "rule_version",
            "scope_type",
            "scope_id",
            name="uq_achievement_grants_rule_scope",
        ),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "business_location_id",
        "rule_key",
        "earned_at",
    ):
        op.create_index(
            f"ix_achievement_grants_{column}",
            "achievement_grants",
            [column],
        )
    op.create_index(
        "ix_achievement_grants_org_earned",
        "achievement_grants",
        ["organization_id", "earned_at"],
    )
    op.create_index(
        "ix_achievement_grants_location_earned",
        "achievement_grants",
        ["business_location_id", "earned_at"],
    )

    op.create_table(
        "achievement_preferences",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column(
            "celebrations_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            name="uq_achievement_preferences_tenant_user",
        ),
    )
    for column in ("tenant_id", "organization_id", "user_id"):
        op.create_index(
            f"ix_achievement_preferences_{column}",
            "achievement_preferences",
            [column],
        )
    op.create_index(
        "ix_achievement_preferences_org_user",
        "achievement_preferences",
        ["organization_id", "user_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in ("achievement_grants", "achievement_preferences"):
            op.execute(
                sa.text(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO lsos_app"
                )
            )
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
    op.drop_table("achievement_preferences")
    op.drop_table("achievement_grants")
