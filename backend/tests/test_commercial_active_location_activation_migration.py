from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260815_0156_enforce_active_location_allowance.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "enforce_active_location_allowance_0156", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(connection, callback) -> None:
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        callback()


def _create_tables(connection) -> dict[str, sa.Table]:
    metadata = sa.MetaData()
    organizations = sa.Table(
        "organizations",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_type", sa.String(30), nullable=False),
    )
    entitlements = sa.Table(
        "entitlements",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("value_type", sa.String(20), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=True),
        sa.Column("reset_period", sa.String(20), nullable=False),
        sa.Column("is_enforced", sa.Boolean(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("deterministic_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("organization_id", "code"),
    )
    activations = sa.Table(
        "commercial_feature_activations",
        metadata,
        sa.Column("code", sa.String(80), primary_key=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("catalog_version", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    business_locations = sa.Table(
        "business_locations",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
    )
    metadata.create_all(connection)
    return {
        "organizations": organizations,
        "entitlements": entitlements,
        "activations": activations,
        "business_locations": business_locations,
    }


def _seed_ready_state(connection, tables, migration) -> None:
    now = datetime.now(UTC)
    plans = {
        "org-solo": ("solo", 1),
        "org-growth": ("growth", 10),
        "org-enterprise": ("enterprise", 20),
        "org-internal": ("internal_anchor", 20),
    }
    connection.execute(
        tables["organizations"].insert(),
        [
            {"id": organization_id, "plan_type": plan_type}
            for organization_id, (plan_type, _limit) in plans.items()
        ],
    )
    entitlement_rows = []
    for organization_id, (_plan_type, limit) in plans.items():
        payload = {
            "organization_id": organization_id,
            "code": migration._ACTIVE_LOCATION_CODE,
            "value_type": "integer",
            "limit_value": limit,
            "reset_period": "none",
            "is_enforced": True,
            "config_json": {
                "catalog_version": migration._CATALOG_VERSION,
                "unit": "business_location",
            },
        }
        entitlement_rows.append(
            {
                "id": f"allowance-{organization_id}",
                **payload,
                "deterministic_hash": migration._stable_hash(payload),
            }
        )
    connection.execute(tables["entitlements"].insert(), entitlement_rows)
    connection.execute(
        tables["activations"].insert().values(
            code=migration._ACTIVATION_CODE,
            state=migration._OBSERVE,
            catalog_version=migration._CATALOG_VERSION,
            created_at=now,
            updated_at=now,
        )
    )
    # Existing overage is preserved. Enforcement blocks future work; it does
    # not delete or silently choose among saved locations.
    connection.execute(
        tables["business_locations"].insert(),
        [
            {
                "id": f"solo-location-{index}",
                "organization_id": "org-solo",
                "name": f"Saved Solo Location {index}",
                "status": "active",
            }
            for index in range(1, 3)
        ],
    )


def test_activation_flips_only_state_and_rollback_restores_observe() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        tables = _create_tables(connection)
        _seed_ready_state(connection, tables, migration)
        organizations_before = connection.execute(
            sa.select(tables["organizations"]).order_by(tables["organizations"].c.id)
        ).mappings().all()
        entitlements_before = connection.execute(
            sa.select(tables["entitlements"]).order_by(tables["entitlements"].c.id)
        ).mappings().all()
        locations_before = connection.execute(
            sa.select(tables["business_locations"]).order_by(
                tables["business_locations"].c.id
            )
        ).mappings().all()

        _run(connection, migration.upgrade)
        assert connection.execute(
            sa.select(tables["activations"].c.state)
        ).scalar_one() == migration._ENFORCED
        assert connection.execute(
            sa.select(tables["organizations"]).order_by(tables["organizations"].c.id)
        ).mappings().all() == organizations_before
        assert connection.execute(
            sa.select(tables["entitlements"]).order_by(tables["entitlements"].c.id)
        ).mappings().all() == entitlements_before
        assert connection.execute(
            sa.select(tables["business_locations"]).order_by(
                tables["business_locations"].c.id
            )
        ).mappings().all() == locations_before

        _run(connection, migration.downgrade)
        assert connection.execute(
            sa.select(tables["activations"].c.state)
        ).scalar_one() == migration._OBSERVE
        assert connection.execute(
            sa.select(sa.func.count()).select_from(tables["business_locations"])
        ).scalar_one() == 2


@pytest.mark.parametrize(
    ("invalid_case", "message"),
    [
        ("missing_allowance", "missing its active-location allowance"),
        ("wrong_limit", "stale or corrupted"),
        ("wrong_hash", "stale or corrupted"),
        ("unknown_plan", "unsupported commercial plan"),
        ("wrong_catalog", "activation catalog is invalid"),
        ("already_enforced", "expected activation state 'observe'"),
    ],
)
def test_activation_preflight_fails_without_changing_state(
    invalid_case: str,
    message: str,
) -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        tables = _create_tables(connection)
        _seed_ready_state(connection, tables, migration)
        if invalid_case == "missing_allowance":
            connection.execute(
                tables["entitlements"].delete().where(
                    tables["entitlements"].c.organization_id == "org-solo"
                )
            )
        elif invalid_case == "wrong_limit":
            connection.execute(
                tables["entitlements"].update()
                .where(tables["entitlements"].c.organization_id == "org-solo")
                .values(limit_value=999)
            )
        elif invalid_case == "wrong_hash":
            connection.execute(
                tables["entitlements"].update()
                .where(tables["entitlements"].c.organization_id == "org-solo")
                .values(deterministic_hash="not-the-saved-payload-hash")
            )
        elif invalid_case == "unknown_plan":
            connection.execute(
                tables["organizations"].update()
                .where(tables["organizations"].c.id == "org-solo")
                .values(plan_type="custom")
            )
        elif invalid_case == "wrong_catalog":
            connection.execute(
                tables["activations"].update().values(catalog_version="unknown")
            )
        elif invalid_case == "already_enforced":
            connection.execute(
                tables["activations"].update().values(state=migration._ENFORCED)
            )

        with pytest.raises(RuntimeError, match=message):
            _run(connection, migration.upgrade)

        expected_state = (
            migration._ENFORCED if invalid_case == "already_enforced" else migration._OBSERVE
        )
        assert connection.execute(
            sa.select(tables["activations"].c.state)
        ).scalar_one() == expected_state
        assert connection.execute(
            sa.select(sa.func.count()).select_from(tables["business_locations"])
        ).scalar_one() == 2
