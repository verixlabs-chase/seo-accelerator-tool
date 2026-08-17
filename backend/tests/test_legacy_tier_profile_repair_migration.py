from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa

from app.domain.commercial_tiers import legacy_entitlement_template
from app.services.tier_profile_service import compute_tier_profile_hash


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260817_0163_restore_legacy_tier_profiles.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("legacy_tier_profile_repair_0163", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_table(connection) -> sa.Table:  # noqa: ANN001
    metadata = sa.MetaData()
    table = sa.Table(
        "tier_profiles",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tier_code", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("entitlement_template_json", sa.JSON(), nullable=False),
        sa.Column("deterministic_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tier_code", "version"),
    )
    metadata.create_all(connection)
    return table


def _run(connection, operation) -> None:  # noqa: ANN001
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        operation()


def _profile_row(table: sa.Table, *, tier_code: str, profile_id: str) -> dict[str, object]:
    template = legacy_entitlement_template()
    return {
        "id": profile_id,
        "tier_code": tier_code,
        "display_name": tier_code.replace("_", " ").title(),
        "version": 1,
        "entitlement_template_json": template,
        "deterministic_hash": compute_tier_profile_hash(
            {
                "tier_code": tier_code,
                "version": 1,
                "entitlements": template["entitlements"],
            }
        ),
        "is_active": True,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }


def test_repair_restores_only_missing_immutable_legacy_profiles() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        table = _create_table(connection)
        historical_standard_id = "historical-standard-v1"
        connection.execute(
            table.insert().values(
                **_profile_row(
                    table,
                    tier_code="standard",
                    profile_id=historical_standard_id,
                )
            )
        )

        _run(connection, migration.upgrade)
        rows = connection.execute(
            sa.select(table).where(table.c.version == 1).order_by(table.c.tier_code)
        ).mappings().all()

        assert [row.tier_code for row in rows] == [
            "enterprise",
            "internal_anchor",
            "standard",
        ]
        assert next(row.id for row in rows if row.tier_code == "standard") == historical_standard_id
        for row in rows:
            migration._validate_existing_profile(row, tier_code=row.tier_code)

        _run(connection, migration.upgrade)
        assert connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 3
        _run(connection, migration.downgrade)
        assert connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 3


def test_repair_preflights_conflicts_before_inserting_any_profile() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        table = _create_table(connection)
        connection.execute(
            table.insert().values(
                id=migration._PROFILE_DEFINITIONS["enterprise"]["id"],
                tier_code="custom",
                display_name="Custom",
                version=9,
                entitlement_template_json={"entitlements": []},
                deterministic_hash="f" * 64,
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )

        with pytest.raises(RuntimeError, match="canonical ID is already used"):
            _run(connection, migration.upgrade)

        assert connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 1
