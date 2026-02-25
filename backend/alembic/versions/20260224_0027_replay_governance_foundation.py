"""strategy replay governance and idempotency foundation

Revision ID: 20260224_0027
Revises: 20260223_0026
Create Date: 2026-02-24 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "20260224_0027"
down_revision: Union[str, None] = "20260223_0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_cols = {column["name"] for column in inspector.get_columns("strategy_recommendations")}
    with op.batch_alter_table("strategy_recommendations") as batch_op:
        if "engine_version" not in existing_cols:
            batch_op.add_column(sa.Column("engine_version", sa.String(length=64), nullable=True))
        if "threshold_bundle_version" not in existing_cols:
            batch_op.add_column(sa.Column("threshold_bundle_version", sa.String(length=64), nullable=True))
        if "registry_version" not in existing_cols:
            batch_op.add_column(sa.Column("registry_version", sa.String(length=64), nullable=True))
        if "signal_schema_version" not in existing_cols:
            batch_op.add_column(sa.Column("signal_schema_version", sa.String(length=64), nullable=True))
        if "input_hash" not in existing_cols:
            batch_op.add_column(sa.Column("input_hash", sa.String(length=64), nullable=True))
        if "output_hash" not in existing_cols:
            batch_op.add_column(sa.Column("output_hash", sa.String(length=64), nullable=True))
        if "build_hash" not in existing_cols:
            batch_op.add_column(sa.Column("build_hash", sa.String(length=64), nullable=True))
        if "idempotency_key" not in existing_cols:
            batch_op.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))

    op.create_table(
        "strategy_execution_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("operation_type", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("version_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("output_hash", sa.String(length=64), nullable=True),
        sa.Column("output_payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "operation_type",
            "idempotency_key",
            name="uq_strategy_exec_tenant_operation_idempotency",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "operation_type",
            "input_hash",
            "version_fingerprint",
            name="uq_strategy_exec_tenant_operation_input_version",
        ),
    )
    op.create_index("ix_strategy_execution_keys_tenant", "strategy_execution_keys", ["tenant_id"], unique=False)
    op.create_index("ix_strategy_execution_keys_campaign", "strategy_execution_keys", ["campaign_id"], unique=False)

    op.create_table(
        "threshold_bundles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version", name="uq_threshold_bundles_version"),
    )
    op.create_index("ix_threshold_bundles_status", "threshold_bundles", ["status"], unique=False)

    with op.batch_alter_table("strategy_recommendations") as batch_op:
        batch_op.create_unique_constraint(
            "uq_strategy_recommendations_idempotency",
            ["tenant_id", "campaign_id", "idempotency_key"],
        )

    dialect = bind.dialect.name.lower()
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
            DROP TRIGGER IF EXISTS trg_strategy_output_immutability ON strategy_recommendations;
            CREATE TRIGGER trg_strategy_output_immutability
            BEFORE UPDATE ON strategy_recommendations
            FOR EACH ROW
            EXECUTE FUNCTION enforce_strategy_output_immutability();
            """
        )
    else:
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_strategy_output_immutability
            BEFORE UPDATE ON strategy_recommendations
            FOR EACH ROW
            WHEN OLD.status IN ('FINAL', 'final')
            BEGIN
                SELECT RAISE(ABORT, 'Immutable strategy output: updates are forbidden for final records');
            END;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name.lower()

    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_strategy_output_immutability ON strategy_recommendations;")
        op.execute("DROP FUNCTION IF EXISTS enforce_strategy_output_immutability();")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_strategy_output_immutability;")

    with op.batch_alter_table("strategy_recommendations") as batch_op:
        batch_op.drop_constraint("uq_strategy_recommendations_idempotency", type_="unique")

    op.drop_index("ix_threshold_bundles_status", table_name="threshold_bundles")
    op.drop_table("threshold_bundles")

    op.drop_index("ix_strategy_execution_keys_campaign", table_name="strategy_execution_keys")
    op.drop_index("ix_strategy_execution_keys_tenant", table_name="strategy_execution_keys")
    op.drop_table("strategy_execution_keys")

    with op.batch_alter_table("strategy_recommendations") as batch_op:
        for column_name in [
            "idempotency_key",
            "build_hash",
            "output_hash",
            "input_hash",
            "signal_schema_version",
            "registry_version",
            "threshold_bundle_version",
            "engine_version",
        ]:
            batch_op.drop_column(column_name)
