"""add immutable governed policy candidates and replays

Revision ID: 20260814_0152
Revises: 20260814_0151
Create Date: 2026-08-14 17:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260814_0152"
down_revision = "20260814_0151"
branch_labels = None
depends_on = None


TABLES = (
    "governed_policy_candidates",
    "governed_policy_replays",
    "governed_policy_decisions",
)


def _tenant_policy(table_name: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    expression = (
        "current_setting('app.platform_access', true) = 'on' OR ("
        "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
        "organization_id::text = current_setting('app.current_organization_id', true))"
    )
    op.execute(sa.text(f"GRANT SELECT, INSERT ON TABLE public.{table_name} TO lsos_app"))
    op.execute(sa.text(f"REVOKE UPDATE, DELETE ON TABLE public.{table_name} FROM lsos_app"))
    op.execute(sa.text(f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY lsos_tenant_isolation ON public.{table_name} "
            f"FOR ALL TO lsos_app USING ({expression}) WITH CHECK ({expression})"
        )
    )


def _immutable_triggers() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.prevent_governed_policy_artifact_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF current_setting('app.platform_maintenance', true) IS DISTINCT FROM 'on'
                THEN
                    RAISE EXCEPTION 'governed policy artifacts are append-only and immutable';
                END IF;
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
    )
    for table_name in TABLES:
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_{table_name}_immutable
                BEFORE UPDATE OR DELETE ON public.{table_name}
                FOR EACH ROW
                EXECUTE FUNCTION public.prevent_governed_policy_artifact_mutation()
                """
            )
        )


def upgrade() -> None:
    op.create_table(
        "governed_policy_candidates",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=True),
        sa.Column("protocol_id", sa.String(36), nullable=False),
        sa.Column("plan_id", sa.String(36), nullable=False),
        sa.Column("policy_family", sa.String(64), nullable=False),
        sa.Column("candidate_version", sa.String(40), nullable=False),
        sa.Column("champion_rule", sa.JSON(), nullable=False),
        sa.Column("challenger_rule", sa.JSON(), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("protocol_hash", sa.String(64), nullable=False),
        sa.Column("candidate_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column(
            "automatic_activation_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "policy_family = 'action_learning_eligibility'",
            name="ck_governed_policy_candidates_family",
        ),
        sa.CheckConstraint(
            "automatic_activation_allowed = false",
            name="ck_governed_policy_candidates_no_activation",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["protocol_id"], ["governed_experiment_protocols.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["governed_experiment_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "protocol_id",
            "policy_family",
            name="uq_governed_policy_candidates_tenant_protocol_family",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_governed_policy_candidates_tenant_idempotency",
        ),
    )
    for column_name in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "protocol_id",
        "plan_id",
        "policy_family",
        "evidence_hash",
        "protocol_hash",
        "candidate_hash",
        "created_at",
    ):
        op.create_index(
            f"ix_governed_policy_candidates_{column_name}",
            "governed_policy_candidates",
            [column_name],
        )
    op.create_index(
        "ix_governed_policy_candidates_campaign_created",
        "governed_policy_candidates",
        ["campaign_id", "created_at"],
    )

    op.create_table(
        "governed_policy_replays",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("replay_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("candidate_hash", sa.String(64), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("ordered_measurement_ids", sa.JSON(), nullable=False),
        sa.Column("cumulative_results", sa.JSON(), nullable=False),
        sa.Column("final_result", sa.JSON(), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column(
            "automatic_activation_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("replayed_by_user_id", sa.String(36), nullable=False),
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('passed','blocked','failed')",
            name="ck_governed_policy_replays_status",
        ),
        sa.CheckConstraint(
            "automatic_activation_allowed = false",
            name="ck_governed_policy_replays_no_activation",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["governed_policy_candidates.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["replayed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_governed_policy_replays_tenant_idempotency",
        ),
    )
    for column_name in (
        "candidate_id",
        "tenant_id",
        "organization_id",
        "campaign_id",
        "status",
        "candidate_hash",
        "evidence_hash",
        "artifact_hash",
        "replayed_at",
    ):
        op.create_index(
            f"ix_governed_policy_replays_{column_name}",
            "governed_policy_replays",
            [column_name],
        )
    op.create_index(
        "ix_governed_policy_replays_candidate_replayed",
        "governed_policy_replays",
        ["candidate_id", "replayed_at"],
    )

    op.create_table(
        "governed_policy_decisions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("replay_id", sa.String(36), nullable=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("acknowledgements", sa.JSON(), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("candidate_hash", sa.String(64), nullable=False),
        sa.Column("replay_artifact_hash", sa.String(64), nullable=True),
        sa.Column("decision_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column(
            "automatic_activation_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("decided_by_user_id", sa.String(36), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision in ('approved_for_future_activation','rejected','cancelled')",
            name="ck_governed_policy_decisions_decision",
        ),
        sa.CheckConstraint(
            "automatic_activation_allowed = false",
            name="ck_governed_policy_decisions_no_activation",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["governed_policy_candidates.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["replay_id"], ["governed_policy_replays.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "candidate_id",
            name="uq_governed_policy_decisions_tenant_candidate",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_governed_policy_decisions_tenant_idempotency",
        ),
    )
    for column_name in (
        "candidate_id",
        "replay_id",
        "tenant_id",
        "organization_id",
        "campaign_id",
        "decision",
        "candidate_hash",
        "replay_artifact_hash",
        "decision_hash",
        "decided_at",
    ):
        op.create_index(
            f"ix_governed_policy_decisions_{column_name}",
            "governed_policy_decisions",
            [column_name],
        )
    op.create_index(
        "ix_governed_policy_decisions_campaign_decided",
        "governed_policy_decisions",
        ["campaign_id", "decided_at"],
    )

    for table_name in TABLES:
        _tenant_policy(table_name)
    _immutable_triggers()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table_name in reversed(TABLES):
            op.execute(
                sa.text(f"DROP TRIGGER IF EXISTS trg_{table_name}_immutable ON public.{table_name}")
            )
            op.execute(
                sa.text(f"DROP POLICY IF EXISTS lsos_tenant_isolation ON public.{table_name}")
            )
            op.execute(sa.text(f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text("DROP FUNCTION IF EXISTS public.prevent_governed_policy_artifact_mutation()")
        )
    op.drop_table("governed_policy_decisions")
    op.drop_table("governed_policy_replays")
    op.drop_table("governed_policy_candidates")
