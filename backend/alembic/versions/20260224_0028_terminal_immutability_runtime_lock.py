"""terminal-state immutability lock and runtime version lock

Revision ID: 20260224_0028
Revises: 20260224_0027
Create Date: 2026-02-24 11:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision: str = "20260224_0028"
down_revision: Union[str, None] = "20260224_0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ALLOWED_STATES = (
    "'DRAFT', 'GENERATED', 'VALIDATED', 'APPROVED', 'SCHEDULED', "
    "'EXECUTED', 'FAILED', 'ROLLED_BACK', 'ARCHIVED'"
)
_TERMINAL_STATES = "'EXECUTED', 'FAILED', 'ROLLED_BACK', 'ARCHIVED'"


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name.lower()
    inspector = inspect(bind)

    if dialect == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'strategy_recommendation_status') THEN
                    CREATE TYPE strategy_recommendation_status AS ENUM (
                        'DRAFT', 'GENERATED', 'VALIDATED', 'APPROVED', 'SCHEDULED',
                        'EXECUTED', 'FAILED', 'ROLLED_BACK', 'ARCHIVED'
                    );
                END IF;
            END
            $$;
            """
        )
        op.execute(
            """
            ALTER TABLE strategy_recommendations
            ALTER COLUMN status TYPE strategy_recommendation_status
            USING status::strategy_recommendation_status
            """
        )
    else:
        with op.batch_alter_table("strategy_recommendations") as batch_op:
            try:
                batch_op.drop_constraint("ck_strategy_recommendations_status_values", type_="check")
            except Exception:
                pass
            batch_op.create_check_constraint("ck_strategy_recommendations_status_values", f"status IN ({_ALLOWED_STATES})")

    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_strategy_output_immutability ON strategy_recommendations")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_strategy_output_immutability")

    if dialect == "postgresql":
        op.execute(
            f"""
            CREATE OR REPLACE FUNCTION enforce_strategy_output_immutability()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF OLD.status IN ({_TERMINAL_STATES})
                   AND current_setting('app.strategy_override', true) IS DISTINCT FROM 'on' THEN
                    RAISE EXCEPTION 'Immutable terminal strategy output record: %', OLD.id;
                END IF;
                RETURN NEW;
            END;
            $$;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_strategy_output_immutability
            BEFORE UPDATE ON strategy_recommendations
            FOR EACH ROW
            EXECUTE FUNCTION enforce_strategy_output_immutability();
            """
        )

        op.execute(
            """
            CREATE OR REPLACE FUNCTION governed_override_strategy_recommendation(
                p_recommendation_id TEXT,
                p_actor_user_id TEXT,
                p_reason TEXT,
                p_new_status strategy_recommendation_status,
                p_new_rationale TEXT DEFAULT NULL
            )
            RETURNS VOID
            LANGUAGE plpgsql
            SECURITY DEFINER
            AS $$
            DECLARE
                v_old strategy_recommendations%ROWTYPE;
            BEGIN
                IF p_reason IS NULL OR btrim(p_reason) = '' THEN
                    RAISE EXCEPTION 'Override reason is required';
                END IF;

                SELECT * INTO v_old
                FROM strategy_recommendations
                WHERE id = p_recommendation_id
                FOR UPDATE;

                IF NOT FOUND THEN
                    RAISE EXCEPTION 'Strategy recommendation not found: %', p_recommendation_id;
                END IF;

                IF v_old.status NOT IN ('EXECUTED', 'FAILED', 'ROLLED_BACK', 'ARCHIVED') THEN
                    RAISE EXCEPTION 'Override allowed only for terminal records. Current status: %', v_old.status;
                END IF;

                PERFORM set_config('app.strategy_override', 'on', true);

                UPDATE strategy_recommendations
                SET status = p_new_status,
                    rationale = COALESCE(p_new_rationale, rationale)
                WHERE id = p_recommendation_id;

                INSERT INTO audit_logs (
                    id,
                    tenant_id,
                    actor_user_id,
                    event_type,
                    payload_json,
                    created_at
                )
                VALUES (
                    substr(md5(random()::text || clock_timestamp()::text), 1, 36),
                    v_old.tenant_id,
                    p_actor_user_id,
                    'strategy.override',
                    json_build_object(
                        'recommendation_id', p_recommendation_id,
                        'reason', p_reason,
                        'old_status', v_old.status,
                        'new_status', p_new_status,
                        'old_rationale', v_old.rationale,
                        'new_rationale', COALESCE(p_new_rationale, v_old.rationale)
                    )::text,
                    now()
                );
            END;
            $$;
            """
        )
    else:
        op.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_strategy_output_immutability
            BEFORE UPDATE ON strategy_recommendations
            FOR EACH ROW
            WHEN OLD.status IN ({_TERMINAL_STATES})
            BEGIN
                SELECT RAISE(ABORT, 'Immutable terminal strategy output record');
            END;
            """
        )

    if not inspector.has_table("runtime_version_locks"):
        op.create_table(
            "runtime_version_locks",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("expected_schema_revision", sa.String(length=40), nullable=False),
            sa.Column("expected_code_fingerprint", sa.String(length=120), nullable=False),
            sa.Column("expected_registry_version", sa.String(length=120), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("id"),
        )

    active_count = bind.execute(text("SELECT count(*) FROM runtime_version_locks WHERE active = true")).scalar_one()
    if int(active_count) == 0:
        bind.execute(
            text(
                """
                INSERT INTO runtime_version_locks (
                    id,
                    expected_schema_revision,
                    expected_code_fingerprint,
                    expected_registry_version,
                    active
                ) VALUES (
                    :id,
                    :schema,
                    :code,
                    :registry,
                    true
                )
                """
            ),
            {
                "id": "runtime-lock-20260224-0028",
                "schema": "20260224_0028",
                "code": "dev",
                "registry": "scenario-registry-v1",
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name.lower()

    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_strategy_output_immutability ON strategy_recommendations")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_strategy_output_immutability")

    if dialect == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS governed_override_strategy_recommendation(TEXT, TEXT, TEXT, strategy_recommendation_status, TEXT)")
        op.execute("DROP FUNCTION IF EXISTS enforce_strategy_output_immutability()")
        op.execute(
            """
            ALTER TABLE strategy_recommendations
            ALTER COLUMN status TYPE VARCHAR(40)
            USING status::text
            """
        )
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_strategy_output_immutability")

    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION enforce_strategy_output_immutability()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF OLD.status IN ('FINAL', 'final') THEN
                    RAISE EXCEPTION 'Immutable strategy output: updates are forbidden for final records';
                END IF;
                RETURN NEW;
            END;
            $$;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_strategy_output_immutability
            BEFORE UPDATE ON strategy_recommendations
            FOR EACH ROW
            EXECUTE FUNCTION enforce_strategy_output_immutability();
            """
        )
    else:
        op.execute(
            """
            CREATE TRIGGER trg_strategy_output_immutability
            BEFORE UPDATE ON strategy_recommendations
            FOR EACH ROW
            WHEN OLD.status IN ('FINAL', 'final')
            BEGIN
                SELECT RAISE(ABORT, 'Immutable strategy output: updates are forbidden for final records');
            END;
            """
        )

    op.drop_table("runtime_version_locks")
