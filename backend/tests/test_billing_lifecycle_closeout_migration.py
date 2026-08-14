import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.organization import Organization


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260814_0154_billing_lifecycle_closeout.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("billing_lifecycle_closeout_0154", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_legacy_organizations_table(connection) -> sa.Table:
    metadata = sa.MetaData()
    table = sa.Table(
        "organizations",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("billing_status", sa.String(40), nullable=True),
        sa.Column("billing_last_event_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
    )
    sa.Index("ix_organizations_stripe_customer_id", table.c.stripe_customer_id)
    sa.Index("ix_organizations_stripe_subscription_id", table.c.stripe_subscription_id)
    metadata.create_all(connection)
    return table


def test_billing_lifecycle_closeout_migration_matches_unique_provider_indexes() -> None:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")

    assert 'revision = "20260814_0154"' in migration
    assert 'down_revision = "20260814_0153"' in migration
    assert 'sa.Column("billing_last_checkout_request_id", sa.String(128), nullable=True)' in migration
    assert 'sa.Column("billing_last_checkout_session_id", sa.String(255), nullable=True)' in migration
    assert 'sa.Column("billing_last_checkout_plan_code", sa.String(30), nullable=True)' in migration
    assert 'sa.Column("billing_pending_checkout_request_id", sa.String(128), nullable=True)' in migration
    assert 'sa.Column("billing_pending_checkout_session_id", sa.String(255), nullable=True)' in migration
    assert 'sa.Column("billing_pending_checkout_plan_code", sa.String(30), nullable=True)' in migration
    assert '"billing_pending_checkout_expires_at"' in migration
    assert 'sa.Column("billing_subscription_status", sa.String(40), nullable=True)' in migration
    assert '"billing_subscription_event_created_at"' in migration
    assert 'sa.Column("billing_subscription_event_type", sa.String(120), nullable=True)' in migration
    assert 'sa.Column("billing_payment_status", sa.String(40), nullable=True)' in migration
    assert '"billing_payment_event_created_at"' in migration
    assert 'sa.Column("billing_payment_event_type", sa.String(120), nullable=True)' in migration
    assert "billing_subscription_status = billing_status" in migration
    assert "billing_subscription_status = 'active'" in migration
    assert "billing_subscription_event_type = 'legacy.recovery_inferred'" in migration
    assert "stripe_subscription_id IS NOT NULL" in migration
    assert "billing_payment_status = billing_status" in migration
    assert "_assert_unique_external_ids()" in migration
    assert "HAVING COUNT(*) > 1" in migration
    assert "duplicate non-null" in migration
    assert "without mutation" in migration
    assert migration.count('"ix_organizations_stripe_customer_id"') >= 4
    assert migration.count('"ix_organizations_stripe_subscription_id"') >= 4
    assert migration.count("unique=True") == 2
    assert migration.count("unique=False") == 2

    indexes = {index.name: index for index in Organization.__table__.indexes}
    assert indexes["ix_organizations_stripe_customer_id"].unique is True
    assert indexes["ix_organizations_stripe_subscription_id"].unique is True
    assert Organization.__table__.c.billing_last_checkout_request_id.type.length == 128
    assert Organization.__table__.c.billing_last_checkout_session_id.type.length == 255
    assert Organization.__table__.c.billing_last_checkout_plan_code.type.length == 30
    assert Organization.__table__.c.billing_pending_checkout_request_id.type.length == 128
    assert Organization.__table__.c.billing_pending_checkout_session_id.type.length == 255
    assert Organization.__table__.c.billing_pending_checkout_plan_code.type.length == 30
    assert Organization.__table__.c.billing_subscription_status.type.length == 40
    assert Organization.__table__.c.billing_subscription_event_type.type.length == 120
    assert Organization.__table__.c.billing_payment_status.type.length == 40
    assert Organization.__table__.c.billing_payment_event_type.type.length == 120


def test_migration_backfills_connected_legacy_recovery_as_active_subscription(
    monkeypatch,
) -> None:
    migration = _load_migration()
    # The application Alembic environment wraps this method for offline SQL output.
    # A unit-level MigrationContext has no EnvironmentContext proxy, so exercise the
    # revision with Alembic's original operation method when that wrapper is active.
    batch_alter_table = Operations.batch_alter_table
    original_batch_alter_table = batch_alter_table.__globals__.get(
        "_original_batch_alter_table"
    )
    if original_batch_alter_table is not None:
        monkeypatch.setattr(
            Operations,
            "batch_alter_table",
            original_batch_alter_table,
        )
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        organizations = _create_legacy_organizations_table(connection)
        legacy_event_time = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
        connection.execute(
            organizations.insert(),
            [
                {
                    "id": "org-connected-recovery",
                    "billing_status": "past_due",
                    "billing_last_event_created_at": legacy_event_time,
                    "stripe_customer_id": "cus_connected_recovery",
                    "stripe_subscription_id": "sub_connected_recovery",
                },
                {
                    "id": "org-no-subscription",
                    "billing_status": "payment_action_required",
                    "billing_last_event_created_at": legacy_event_time,
                    "stripe_customer_id": "cus_no_subscription",
                    "stripe_subscription_id": None,
                },
            ],
        )
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()

        rows = {
            row.id: row
            for row in connection.execute(
                sa.text(
                    """
                    SELECT id,
                           billing_subscription_status,
                           billing_subscription_event_type,
                           billing_payment_status,
                           billing_payment_event_type
                    FROM organizations
                    """
                )
            ).mappings()
        }
        connected = rows["org-connected-recovery"]
        assert connected.billing_subscription_status == "active"
        assert connected.billing_subscription_event_type == "legacy.recovery_inferred"
        assert connected.billing_payment_status == "past_due"
        assert connected.billing_payment_event_type == "legacy.migrated"
        no_subscription = rows["org-no-subscription"]
        assert no_subscription.billing_subscription_status is None
        assert no_subscription.billing_payment_status == "payment_action_required"


def test_migration_fails_before_mutation_when_external_ids_are_duplicated() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        organizations = _create_legacy_organizations_table(connection)
        connection.execute(
            organizations.insert(),
            [
                {
                    "id": "org-duplicate-one",
                    "stripe_subscription_id": "sub_existing_duplicate",
                },
                {
                    "id": "org-duplicate-two",
                    "stripe_subscription_id": "sub_existing_duplicate",
                },
            ],
        )
        context = MigrationContext.configure(connection)
        with pytest.raises(
            RuntimeError,
            match="duplicate non-null stripe_subscription_id values",
        ):
            with Operations.context(context):
                migration.upgrade()

        column_names = {
            column["name"] for column in sa.inspect(connection).get_columns("organizations")
        }
        assert "billing_subscription_status" not in column_names
        duplicate_values = connection.execute(
            sa.text(
                """
                SELECT stripe_subscription_id
                FROM organizations
                ORDER BY id
                """
            )
        ).scalars().all()
        assert duplicate_values == ["sub_existing_duplicate", "sub_existing_duplicate"]
