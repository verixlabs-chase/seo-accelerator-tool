"""add paid local search rank-grid scans

Revision ID: 20260805_0097
Revises: 20260804_0096
Create Date: 2026-08-05 09:00:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260805_0097"
down_revision = "20260804_0096"
branch_labels = None
depends_on = None


PRICE_CARD_ID = "97b28159-6102-4a1d-b1ab-cb58d7eb8d97"


def upgrade() -> None:
    op.create_table(
        "local_rank_grid_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("business_location_id", sa.String(36), sa.ForeignKey("business_locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("grid_size", sa.Integer(), nullable=False),
        sa.Column("radius_miles", sa.Numeric(6, 2), nullable=False),
        sa.Column("center_latitude", sa.Numeric(10, 7), nullable=False),
        sa.Column("center_longitude", sa.Numeric(10, 7), nullable=False),
        sa.Column("provider_location_code", sa.String(32), nullable=False),
        sa.Column("provider_location_name", sa.String(255), nullable=False),
        sa.Column("provider_location_type", sa.String(50), nullable=True),
        sa.Column("keyword_snapshot", sa.JSON(), nullable=False),
        sa.Column("keyword_count", sa.Integer(), nullable=False),
        sa.Column("total_checks", sa.Integer(), nullable=False),
        sa.Column("completed_checks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_checks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("not_found_checks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_mode", sa.String(32), nullable=False),
        sa.Column("credential_owner", sa.String(20), nullable=True),
        sa.Column("reservation_id", sa.String(36), sa.ForeignKey("cost_ledger_entries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("provider_reported_cost", sa.Numeric(18, 8), nullable=True),
        sa.Column("estimated_credit_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_business_name", sa.String(255), nullable=False),
        sa.Column("target_domain", sa.String(320), nullable=True),
        sa.Column("source_name", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_local_rank_grid_runs_org_idempotency"),
        sa.CheckConstraint("status in ('queued','submitting','pending','partial','completed','failed')", name="ck_local_rank_grid_runs_status"),
        sa.CheckConstraint("grid_size in (3,5,7)", name="ck_local_rank_grid_runs_grid_size"),
        sa.CheckConstraint("radius_miles >= 1 and radius_miles <= 25", name="ck_local_rank_grid_runs_radius"),
    )
    op.create_index("ix_local_rank_grid_runs_tenant_id", "local_rank_grid_runs", ["tenant_id"])
    op.create_index("ix_local_rank_grid_runs_organization_id", "local_rank_grid_runs", ["organization_id"])
    op.create_index("ix_local_rank_grid_runs_campaign_id", "local_rank_grid_runs", ["campaign_id"])
    op.create_index("ix_local_rank_grid_runs_business_location_id", "local_rank_grid_runs", ["business_location_id"])
    op.create_index("ix_local_rank_grid_runs_status", "local_rank_grid_runs", ["status"])
    op.create_index("ix_local_rank_grid_runs_created_at", "local_rank_grid_runs", ["created_at"])
    op.create_index("ix_local_rank_grid_runs_campaign_created", "local_rank_grid_runs", ["campaign_id", "created_at"])

    op.create_table(
        "local_rank_grid_points",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("local_rank_grid_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("business_location_id", sa.String(36), sa.ForeignKey("business_locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keyword_id", sa.String(36), sa.ForeignKey("campaign_keywords.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("grid_index", sa.Integer(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("column_index", sa.Integer(), nullable=False),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=False),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("matched_business_name", sa.String(255), nullable=True),
        sa.Column("matched_business_domain", sa.String(320), nullable=True),
        sa.Column("source_name", sa.String(64), nullable=False),
        sa.Column("provider_task_id", sa.String(80), nullable=True, unique=True),
        sa.Column("provider_status_code", sa.Integer(), nullable=True),
        sa.Column("provider_status_message", sa.String(255), nullable=True),
        sa.Column("provider_reported_cost", sa.Numeric(18, 8), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "keyword_id", "grid_index", name="uq_local_rank_grid_points_run_keyword_index"),
        sa.CheckConstraint("status in ('queued','pending','ranked','not_found','failed')", name="ck_local_rank_grid_points_status"),
        sa.CheckConstraint("rank is null or rank >= 1", name="ck_local_rank_grid_points_rank"),
    )
    for column in ("run_id", "tenant_id", "organization_id", "campaign_id", "business_location_id", "keyword_id", "status"):
        op.create_index(f"ix_local_rank_grid_points_{column}", "local_rank_grid_points", [column])
    op.create_index("ix_local_rank_grid_points_run_keyword", "local_rank_grid_points", ["run_id", "keyword_id", "grid_index"])

    price_cards = sa.table(
        "provider_price_cards",
        sa.column("id", sa.String), sa.column("provider_name", sa.String),
        sa.column("capability", sa.String), sa.column("operation", sa.String),
        sa.column("model_name", sa.String), sa.column("unit", sa.String),
        sa.column("unit_cost", sa.Numeric),
        sa.column("currency", sa.String), sa.column("version", sa.String),
        sa.column("source_url", sa.String), sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("active", sa.Boolean),
    )
    now = datetime(2026, 8, 4, tzinfo=UTC)
    op.bulk_insert(price_cards, [{
        "id": PRICE_CARD_ID, "provider_name": "dataforseo", "capability": "local_rank_grid",
        "operation": "google_maps_standard", "model_name": "", "unit": "serp_page",
        "unit_cost": 0.0006,
        "currency": "USD", "version": "google-maps-standard-2026-08-04-v1",
        "source_url": "https://dataforseo.com/pricing/serp/google-maps-serp-api",
        "effective_from": now, "active": True,
    }])

    if op.get_bind().dialect.name == "postgresql":
        for table in ("local_rank_grid_runs", "local_rank_grid_points"):
            op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE ON TABLE public.{table} TO lsos_app"))
            op.execute(sa.text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
            op.execute(sa.text(
                f"CREATE POLICY lsos_tenant_isolation ON public.{table} FOR ALL TO lsos_app "
                "USING (current_setting('app.platform_access', true) = 'on' OR "
                "(tenant_id::text = current_setting('app.current_tenant_id', true) AND "
                "organization_id::text = current_setting('app.current_organization_id', true))) "
                "WITH CHECK (current_setting('app.platform_access', true) = 'on' OR "
                "(tenant_id::text = current_setting('app.current_tenant_id', true) AND "
                "organization_id::text = current_setting('app.current_organization_id', true)))"
            ))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM provider_price_cards WHERE id = :id").bindparams(id=PRICE_CARD_ID))
    op.drop_table("local_rank_grid_points")
    op.drop_table("local_rank_grid_runs")
