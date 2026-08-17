"""add provider-neutral AI search visibility foundation

Revision ID: 20260814_0153
Revises: 20260814_0152
Create Date: 2026-08-14 18:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260814_0153"
down_revision = "20260814_0152"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "ai_search_question_sets",
    "ai_search_collection_runs",
    "ai_search_observations",
)
IMMUTABLE_TABLES = (
    "ai_search_engine_registry",
    "ai_search_provider_contract_registry",
    "ai_search_question_sets",
    "ai_search_observations",
)


def _tenant_policy(table_name: str, *, allow_update: bool = False) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    expression = (
        "current_setting('app.platform_access', true) = 'on' OR ("
        "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
        "organization_id::text = current_setting('app.current_organization_id', true))"
    )
    privileges = "SELECT, INSERT, UPDATE" if allow_update else "SELECT, INSERT"
    op.execute(sa.text(f"GRANT {privileges} ON TABLE public.{table_name} TO lsos_app"))
    if allow_update:
        op.execute(sa.text(f"REVOKE DELETE ON TABLE public.{table_name} FROM lsos_app"))
    else:
        op.execute(sa.text(f"REVOKE UPDATE, DELETE ON TABLE public.{table_name} FROM lsos_app"))
    op.execute(sa.text(f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY lsos_tenant_isolation ON public.{table_name} "
            f"FOR ALL TO lsos_app USING ({expression}) WITH CHECK ({expression})"
        )
    )


def _mutation_guards() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.prevent_ai_search_artifact_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF current_setting('app.platform_maintenance', true) IS DISTINCT FROM 'on'
                THEN
                    RAISE EXCEPTION 'AI search artifacts are append-only and immutable';
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
    for table_name in IMMUTABLE_TABLES:
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_{table_name}_immutable
                BEFORE UPDATE OR DELETE ON public.{table_name}
                FOR EACH ROW
                EXECUTE FUNCTION public.prevent_ai_search_artifact_mutation()
                """
            )
        )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.protect_ai_search_run_identity()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF current_setting('app.platform_maintenance', true) = 'on' THEN
                    IF TG_OP = 'DELETE' THEN
                        RETURN OLD;
                    END IF;
                    RETURN NEW;
                END IF;
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'AI search collection runs cannot be deleted';
                END IF;
                IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
                    OR OLD.organization_id IS DISTINCT FROM NEW.organization_id
                    OR OLD.campaign_id IS DISTINCT FROM NEW.campaign_id
                    OR OLD.business_location_id IS DISTINCT FROM NEW.business_location_id
                    OR OLD.question_set_id IS DISTINCT FROM NEW.question_set_id
                    OR OLD.engine_registry_id IS DISTINCT FROM NEW.engine_registry_id
                    OR OLD.provider_contract_id IS DISTINCT FROM NEW.provider_contract_id
                    OR OLD.comparison_version IS DISTINCT FROM NEW.comparison_version
                    OR OLD.collection_contract_version IS DISTINCT FROM NEW.collection_contract_version
                    OR OLD.parser_version IS DISTINCT FROM NEW.parser_version
                    OR OLD.normalizer_version IS DISTINCT FROM NEW.normalizer_version
                    OR OLD.personalization_policy IS DISTINCT FROM NEW.personalization_policy
                    OR OLD.comparison_scope_hash IS DISTINCT FROM NEW.comparison_scope_hash
                    OR OLD.prior_comparable_run_id IS DISTINCT FROM NEW.prior_comparable_run_id
                    OR OLD.location_snapshot IS DISTINCT FROM NEW.location_snapshot
                    OR OLD.language_code IS DISTINCT FROM NEW.language_code
                    OR OLD.device IS DISTINCT FROM NEW.device
                    OR OLD.request_hash IS DISTINCT FROM NEW.request_hash
                    OR OLD.idempotency_key IS DISTINCT FROM NEW.idempotency_key
                    OR OLD.requested_observation_count IS DISTINCT FROM NEW.requested_observation_count
                    OR OLD.price_card_id IS DISTINCT FROM NEW.price_card_id
                    OR OLD.cost_reservation_id IS DISTINCT FROM NEW.cost_reservation_id
                    OR OLD.credential_owner IS DISTINCT FROM NEW.credential_owner
                    OR OLD.requested_at IS DISTINCT FROM NEW.requested_at
                    OR OLD.created_at IS DISTINCT FROM NEW.created_at
                THEN
                    RAISE EXCEPTION 'AI search collection run identity is immutable';
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_ai_search_collection_runs_protect_identity
            BEFORE UPDATE OR DELETE ON public.ai_search_collection_runs
            FOR EACH ROW
            EXECUTE FUNCTION public.protect_ai_search_run_identity()
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.enforce_ai_search_collection_preflight()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM public.ai_search_engine_registry engine
                    WHERE engine.id = NEW.engine_registry_id
                      AND engine.status = 'active'
                      AND engine.customer_visible = true
                      AND engine.evidence_qa_passed = true
                      AND engine.cost_qa_passed = true
                      AND engine.comparison_qa_passed = true
                ) THEN
                    RAISE EXCEPTION 'AI search collection is not configured';
                END IF;
                IF NOT EXISTS (
                    SELECT 1
                    FROM public.ai_search_provider_contract_registry contract
                    WHERE contract.id = NEW.provider_contract_id
                      AND contract.status = 'approved'
                      AND contract.contract_version = NEW.collection_contract_version
                      AND contract.parser_version = NEW.parser_version
                      AND contract.normalizer_version = NEW.normalizer_version
                      AND contract.production_qa_passed = true
                      AND contract.pricing_qa_passed = true
                      AND contract.automatic_activation_allowed = true
                ) THEN
                    RAISE EXCEPTION 'AI search collection is not configured';
                END IF;
                IF NEW.price_card_id IS NULL
                    OR NEW.cost_reservation_id IS NULL
                    OR NEW.credential_owner IS NULL
                THEN
                    RAISE EXCEPTION 'AI search cost controls are not configured';
                END IF;
                IF NOT EXISTS (
                    SELECT 1
                    FROM public.provider_price_cards price
                    WHERE price.id = NEW.price_card_id
                      AND price.active = true
                      AND price.effective_from <= NEW.requested_at
                      AND (price.effective_to IS NULL OR price.effective_to > NEW.requested_at)
                ) THEN
                    RAISE EXCEPTION 'AI search cost controls are not configured';
                END IF;
                IF NOT EXISTS (
                    SELECT 1
                    FROM public.cost_ledger_entries reservation
                    WHERE reservation.id = NEW.cost_reservation_id
                      AND reservation.organization_id = NEW.organization_id
                      AND reservation.event_type = 'reservation'
                      AND reservation.status = 'reserved'
                ) THEN
                    RAISE EXCEPTION 'AI search credit reservation is not configured';
                END IF;

                -- A later activation migration must add a governed plan allowance.
                RAISE EXCEPTION 'AI search usage allowance is not configured';
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_ai_search_collection_runs_preflight
            BEFORE INSERT ON public.ai_search_collection_runs
            FOR EACH ROW
            EXECUTE FUNCTION public.enforce_ai_search_collection_preflight()
            """
        )
    )


def upgrade() -> None:
    op.create_table(
        "ai_search_engine_registry",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("engine_code", sa.String(80), nullable=False),
        sa.Column("public_name", sa.String(120), nullable=False),
        sa.Column("registry_version", sa.String(40), nullable=False),
        sa.Column("collection_method", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("customer_visible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "automatic_activation_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("evidence_qa_passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cost_qa_passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("comparison_qa_passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("supported_geographies", sa.JSON(), nullable=False),
        sa.Column("supported_languages", sa.JSON(), nullable=False),
        sa.Column("supported_devices", sa.JSON(), nullable=False),
        sa.Column("supported_personalization_policies", sa.JSON(), nullable=False),
        sa.Column("supported_evidence_facts", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("qa_approval_reference", sa.String(160), nullable=True),
        sa.Column("production_proof_reference", sa.String(160), nullable=True),
        sa.Column("supersedes_engine_registry_id", sa.String(36), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('candidate','active','paused','retired')",
            name="ck_ai_search_engine_registry_status",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_engine_registry_id"],
            ["ai_search_engine_registry.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "customer_visible = false",
            name="ck_ai_search_engine_registry_customer_visibility_disabled",
        ),
        sa.CheckConstraint(
            "automatic_activation_allowed = false",
            name="ck_ai_search_engine_registry_automatic_activation_disabled",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "engine_code",
            "registry_version",
            name="uq_ai_search_engine_registry_code_version",
        ),
    )
    op.create_index(
        "ix_ai_search_engine_registry_engine_code",
        "ai_search_engine_registry",
        ["engine_code"],
    )
    op.create_index(
        "ix_ai_search_engine_registry_status",
        "ai_search_engine_registry",
        ["status"],
    )
    op.create_index(
        "ix_ai_search_engine_registry_content_hash",
        "ai_search_engine_registry",
        ["content_hash"],
    )
    op.create_index(
        "ix_ai_search_engine_registry_supersedes_engine_registry_id",
        "ai_search_engine_registry",
        ["supersedes_engine_registry_id"],
    )

    op.create_table(
        "ai_search_provider_contract_registry",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("provider_key", sa.String(80), nullable=False),
        sa.Column("contract_code", sa.String(80), nullable=False),
        sa.Column("contract_version", sa.String(40), nullable=False),
        sa.Column("collection_mode", sa.String(40), nullable=False),
        sa.Column("request_schema_version", sa.String(40), nullable=False),
        sa.Column("response_schema_version", sa.String(40), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("normalizer_version", sa.String(64), nullable=False),
        sa.Column("engine_mappings", sa.JSON(), nullable=False),
        sa.Column("required_inputs", sa.JSON(), nullable=False),
        sa.Column("guaranteed_evidence_facts", sa.JSON(), nullable=False),
        sa.Column("optional_evidence_facts", sa.JSON(), nullable=False),
        sa.Column("unsupported_evidence_facts", sa.JSON(), nullable=False),
        sa.Column("raw_response_retention_days", sa.Integer(), nullable=True),
        sa.Column("billable_unit", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("production_qa_passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pricing_qa_passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "automatic_activation_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("qa_approval_reference", sa.String(160), nullable=True),
        sa.Column("production_proof_reference", sa.String(160), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("supersedes_provider_contract_id", sa.String(36), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status = 'candidate'",
            name="ck_ai_search_provider_contract_candidate_only",
        ),
        sa.CheckConstraint(
            "production_qa_passed = false AND pricing_qa_passed = false",
            name="ck_ai_search_provider_contract_qa_disabled",
        ),
        sa.CheckConstraint(
            "automatic_activation_allowed = false",
            name="ck_ai_search_provider_contract_automatic_activation_disabled",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_provider_contract_id"],
            ["ai_search_provider_contract_registry.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_key",
            "contract_code",
            "contract_version",
            name="uq_ai_search_provider_contract_identity",
        ),
    )
    for column_name in (
        "provider_key",
        "contract_code",
        "status",
        "content_hash",
    ):
        op.create_index(
            f"ix_ai_search_provider_contract_registry_{column_name}",
            "ai_search_provider_contract_registry",
            [column_name],
        )
    op.create_index(
        "ix_ai_search_provider_contract_supersedes",
        "ai_search_provider_contract_registry",
        ["supersedes_provider_contract_id"],
    )

    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.create_unique_constraint(
            "uq_campaigns_ai_search_scoped_identity",
            ["id", "tenant_id", "organization_id", "business_location_id"],
        )
    with op.batch_alter_table("users") as batch_op:
        batch_op.create_unique_constraint(
            "uq_users_ai_search_scoped_identity",
            ["id", "tenant_id"],
        )

    op.create_table(
        "ai_search_question_sets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("generator_version", sa.String(64), nullable=False),
        sa.Column("questions", sa.JSON(), nullable=False),
        sa.Column("context_snapshot", sa.JSON(), nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("question_set_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status = 'frozen'", name="ck_ai_search_question_sets_frozen"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            [
                "campaign_id",
                "tenant_id",
                "organization_id",
                "business_location_id",
            ],
            [
                "campaigns.id",
                "campaigns.tenant_id",
                "campaigns.organization_id",
                "campaigns.business_location_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_search_question_sets_scoped_campaign",
        ),
        sa.ForeignKeyConstraint(
            ["business_location_id", "organization_id"],
            ["business_locations.id", "business_locations.organization_id"],
            ondelete="RESTRICT",
            name="fk_ai_search_question_sets_scoped_location",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            ondelete="RESTRICT",
            name="fk_ai_search_question_sets_scoped_creator",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "campaign_id",
            "version",
            name="uq_ai_search_question_sets_scope_version",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "campaign_id",
            "question_set_hash",
            name="uq_ai_search_question_sets_scope_hash",
        ),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            name="uq_ai_search_question_sets_scoped_identity",
        ),
    )
    for column_name in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "context_hash",
        "question_set_hash",
        "status",
    ):
        op.create_index(
            f"ix_ai_search_question_sets_{column_name}",
            "ai_search_question_sets",
            [column_name],
        )
    op.create_index(
        "ix_ai_search_question_sets_campaign_created",
        "ai_search_question_sets",
        ["campaign_id", "created_at"],
    )

    op.create_table(
        "ai_search_collection_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
        sa.Column("question_set_id", sa.String(36), nullable=False),
        sa.Column("engine_registry_id", sa.String(36), nullable=False),
        sa.Column("provider_contract_id", sa.String(36), nullable=False),
        sa.Column("comparison_version", sa.String(64), nullable=False),
        sa.Column("collection_contract_version", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("normalizer_version", sa.String(64), nullable=False),
        sa.Column("personalization_policy", sa.String(80), nullable=False),
        sa.Column("comparison_scope_hash", sa.String(64), nullable=False),
        sa.Column("prior_comparable_run_id", sa.String(36), nullable=True),
        sa.Column("location_snapshot", sa.JSON(), nullable=False),
        sa.Column("language_code", sa.String(16), nullable=False),
        sa.Column("device", sa.String(24), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("safe_error_code", sa.String(80), nullable=True),
        sa.Column("safe_error_message", sa.Text(), nullable=True),
        sa.Column("requested_observation_count", sa.Integer(), nullable=False),
        sa.Column("collected_observation_count", sa.Integer(), nullable=False),
        sa.Column("coverage_summary", sa.JSON(), nullable=False),
        sa.Column("price_card_id", sa.String(36), nullable=True),
        sa.Column("cost_reservation_id", sa.String(36), nullable=True),
        sa.Column("credential_owner", sa.String(20), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in "
            "('queued','submitted','collecting','complete','partial','failed',"
            "'expired','unsupported','unavailable')",
            name="ck_ai_search_collection_runs_status",
        ),
        sa.CheckConstraint(
            "requested_observation_count >= 0 AND collected_observation_count >= 0 "
            "AND collected_observation_count <= requested_observation_count",
            name="ck_ai_search_collection_runs_observation_counts",
        ),
        sa.CheckConstraint(
            "credential_owner IS NULL OR credential_owner in ('platform','organization')",
            name="ck_ai_search_collection_runs_credential_owner",
        ),
        sa.CheckConstraint(
            "(price_card_id IS NULL AND cost_reservation_id IS NULL "
            "AND credential_owner IS NULL) OR "
            "(price_card_id IS NOT NULL AND cost_reservation_id IS NOT NULL "
            "AND credential_owner IS NOT NULL)",
            name="ck_ai_search_collection_runs_cost_provenance_complete",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            [
                "question_set_id",
                "tenant_id",
                "organization_id",
                "campaign_id",
                "business_location_id",
            ],
            [
                "ai_search_question_sets.id",
                "ai_search_question_sets.tenant_id",
                "ai_search_question_sets.organization_id",
                "ai_search_question_sets.campaign_id",
                "ai_search_question_sets.business_location_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_search_collection_runs_scoped_question_set",
        ),
        sa.ForeignKeyConstraint(
            ["engine_registry_id"], ["ai_search_engine_registry.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["provider_contract_id"],
            ["ai_search_provider_contract_registry.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["price_card_id"], ["provider_price_cards.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["cost_reservation_id"], ["cost_ledger_entries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            [
                "prior_comparable_run_id",
                "tenant_id",
                "organization_id",
                "campaign_id",
                "business_location_id",
                "question_set_id",
                "engine_registry_id",
                "provider_contract_id",
            ],
            [
                "ai_search_collection_runs.id",
                "ai_search_collection_runs.tenant_id",
                "ai_search_collection_runs.organization_id",
                "ai_search_collection_runs.campaign_id",
                "ai_search_collection_runs.business_location_id",
                "ai_search_collection_runs.question_set_id",
                "ai_search_collection_runs.engine_registry_id",
                "ai_search_collection_runs.provider_contract_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_search_collection_runs_scoped_prior_run",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "idempotency_key",
            name="uq_ai_search_collection_runs_scope_idempotency",
        ),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            "question_set_id",
            "engine_registry_id",
            "provider_contract_id",
            name="uq_ai_search_collection_runs_scoped_identity",
        ),
    )
    for column_name in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "question_set_id",
        "engine_registry_id",
        "provider_contract_id",
        "comparison_scope_hash",
        "prior_comparable_run_id",
        "status",
        "request_hash",
        "price_card_id",
        "cost_reservation_id",
    ):
        op.create_index(
            f"ix_ai_search_collection_runs_{column_name}",
            "ai_search_collection_runs",
            [column_name],
        )
    op.create_index(
        "ix_ai_search_collection_runs_campaign_requested",
        "ai_search_collection_runs",
        ["campaign_id", "requested_at"],
    )

    op.create_table(
        "ai_search_observations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("question_set_id", sa.String(36), nullable=False),
        sa.Column("engine_registry_id", sa.String(36), nullable=False),
        sa.Column("provider_contract_id", sa.String(36), nullable=False),
        sa.Column("question_id", sa.String(64), nullable=False),
        sa.Column("question_text_hash", sa.String(64), nullable=False),
        sa.Column("collection_contract_version", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("normalizer_version", sa.String(64), nullable=False),
        sa.Column("personalization_policy", sa.String(80), nullable=False),
        sa.Column("model_version", sa.String(120), nullable=True),
        sa.Column("location_snapshot", sa.JSON(), nullable=False),
        sa.Column("language_code", sa.String(16), nullable=False),
        sa.Column("device", sa.String(24), nullable=False),
        sa.Column("mention_state", sa.String(24), nullable=False),
        sa.Column("recommendation_state", sa.String(24), nullable=False),
        sa.Column("citation_state", sa.String(24), nullable=False),
        sa.Column("link_state", sa.String(24), nullable=False),
        sa.Column("response_excerpt", sa.Text(), nullable=True),
        sa.Column("cited_sources", sa.JSON(), nullable=False),
        sa.Column("competitor_entities", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("raw_response_hash", sa.String(64), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mention_state in ('observed','not_observed','not_measured','unavailable')",
            name="ck_ai_search_observations_mention_state",
        ),
        sa.CheckConstraint(
            "recommendation_state in "
            "('observed','not_observed','not_measured','unavailable')",
            name="ck_ai_search_observations_recommendation_state",
        ),
        sa.CheckConstraint(
            "citation_state in ('observed','not_observed','not_measured','unavailable')",
            name="ck_ai_search_observations_citation_state",
        ),
        sa.CheckConstraint(
            "link_state in ('observed','not_observed','not_measured','unavailable')",
            name="ck_ai_search_observations_link_state",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            [
                "run_id",
                "tenant_id",
                "organization_id",
                "campaign_id",
                "business_location_id",
                "question_set_id",
                "engine_registry_id",
                "provider_contract_id",
            ],
            [
                "ai_search_collection_runs.id",
                "ai_search_collection_runs.tenant_id",
                "ai_search_collection_runs.organization_id",
                "ai_search_collection_runs.campaign_id",
                "ai_search_collection_runs.business_location_id",
                "ai_search_collection_runs.question_set_id",
                "ai_search_collection_runs.engine_registry_id",
                "ai_search_collection_runs.provider_contract_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_search_observations_scoped_run",
        ),
        sa.ForeignKeyConstraint(
            ["question_set_id"], ["ai_search_question_sets.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["engine_registry_id"], ["ai_search_engine_registry.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["provider_contract_id"],
            ["ai_search_provider_contract_registry.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "run_id",
            "question_id",
            name="uq_ai_search_observations_run_question",
        ),
    )
    for column_name in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "run_id",
        "question_set_id",
        "engine_registry_id",
        "provider_contract_id",
        "evidence_hash",
        "observed_at",
    ):
        op.create_index(
            f"ix_ai_search_observations_{column_name}",
            "ai_search_observations",
            [column_name],
        )
    op.create_index(
        "ix_ai_search_observations_campaign_observed",
        "ai_search_observations",
        ["campaign_id", "observed_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table_name in (
            "ai_search_engine_registry",
            "ai_search_provider_contract_registry",
        ):
            op.execute(sa.text(f"GRANT SELECT ON TABLE public.{table_name} TO lsos_app"))
            op.execute(
                sa.text(
                    "REVOKE INSERT, UPDATE, DELETE ON TABLE "
                    f"public.{table_name} FROM lsos_app"
                )
            )
    _tenant_policy("ai_search_question_sets")
    _tenant_policy("ai_search_collection_runs", allow_update=True)
    _tenant_policy("ai_search_observations")
    _mutation_guards()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_ai_search_collection_runs_preflight "
                "ON public.ai_search_collection_runs"
            )
        )
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_ai_search_collection_runs_protect_identity "
                "ON public.ai_search_collection_runs"
            )
        )
        for table_name in reversed(IMMUTABLE_TABLES):
            op.execute(
                sa.text(
                    f"DROP TRIGGER IF EXISTS trg_{table_name}_immutable ON public.{table_name}"
                )
            )
        for table_name in reversed(TENANT_TABLES):
            op.execute(
                sa.text(f"DROP POLICY IF EXISTS lsos_tenant_isolation ON public.{table_name}")
            )
            op.execute(sa.text(f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text("DROP FUNCTION IF EXISTS public.prevent_ai_search_artifact_mutation()")
        )
        op.execute(sa.text("DROP FUNCTION IF EXISTS public.protect_ai_search_run_identity()"))
        op.execute(
            sa.text(
                "DROP FUNCTION IF EXISTS public.enforce_ai_search_collection_preflight()"
            )
        )
    op.drop_table("ai_search_observations")
    op.drop_table("ai_search_collection_runs")
    op.drop_table("ai_search_question_sets")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint(
            "uq_users_ai_search_scoped_identity",
            type_="unique",
        )
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.drop_constraint(
            "uq_campaigns_ai_search_scoped_identity",
            type_="unique",
        )
    op.drop_table("ai_search_provider_contract_registry")
    op.drop_table("ai_search_engine_registry")
