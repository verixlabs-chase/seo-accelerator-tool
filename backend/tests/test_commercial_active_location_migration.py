from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa

from app.domain.commercial_tiers import (
    COMMERCIAL_TIER_VERSION,
    COMMERCIAL_TIERS,
    commercial_entitlement_template,
)
from app.models.commercial_feature_activation import CommercialFeatureActivation
from app.services.tier_profile_service import compute_tier_profile_hash


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260814_0155_commercial_active_location_allowance.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "commercial_active_location_allowance_0155", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_legacy_tables(connection) -> dict[str, sa.Table]:
    metadata = sa.MetaData()
    tier_profiles = sa.Table(
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
    organizations = sa.Table(
        "organizations",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_type", sa.String(30), nullable=False),
        sa.Column("tier_profile_id", sa.String(36), nullable=True),
        sa.Column("tier_version", sa.Integer(), nullable=False, default=1),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("organization_id", "code"),
    )
    usage_ledgers = sa.Table(
        "usage_ledgers",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("entitlement_code", sa.String(120), nullable=False),
        sa.Column("usage_value", sa.Integer(), nullable=False),
    )
    metadata.create_all(connection)
    return {
        "tier_profiles": tier_profiles,
        "organizations": organizations,
        "entitlements": entitlements,
        "usage_ledgers": usage_ledgers,
    }


def _run_upgrade(connection, migration) -> None:
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        migration.upgrade()


def _run_downgrade(connection, migration) -> None:
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        migration.downgrade()


def _seed_legacy_profiles(connection, tables, migration) -> dict[str, str]:
    now = datetime.now(UTC)
    rows = migration._legacy_template()
    profile_ids = {
        # Include a valid historical non-preferred identity for Standard. The
        # original 0073 migration intentionally reused such rows.
        "standard": "historical-standard-v1-profile",
        "enterprise": "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690002",
        "internal_anchor": "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690003",
    }
    connection.execute(
        tables["tier_profiles"].insert(),
        [
            {
                "id": profile_id,
                "tier_code": tier_code,
                "display_name": tier_code.replace("_", " ").title(),
                "version": 1,
                "entitlement_template_json": {"entitlements": rows},
                "deterministic_hash": migration._stable_hash(
                    {
                        "tier_code": tier_code,
                        "version": 1,
                        "entitlements": rows,
                    }
                ),
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            for tier_code, profile_id in profile_ids.items()
        ],
    )
    return profile_ids


def test_catalog_v2_runtime_and_migration_templates_have_fixed_hashes() -> None:
    migration = _load_migration()
    expected_hashes = {
        "solo": "a742a14c591d0f5de620962851d82bec44d3ee4d44cba801143e454b9991e256",
        "multi_location": "f384663380a5ca681b34b0500665fb491da398bf4d29d66f3ae9a0fb4dd99f55",
        "enterprise": "fb455d1256982980864c9bf057b19ecc5e704fcc622a97a051270e2609f2fc8b",
        "internal_anchor": "fd701c86ddeae820d13608c6d9a0cd82e9fffdf00d87ea6c3192f76c7b7b1c6b",
    }

    assert set(migration._PROFILE_DEFINITIONS) == set(COMMERCIAL_TIERS)
    for plan_code, definition in COMMERCIAL_TIERS.items():
        runtime_rows = commercial_entitlement_template(plan_code)["entitlements"]
        migration_rows = migration._template(plan_code)
        runtime_hash = compute_tier_profile_hash(
            {
                "tier_code": plan_code,
                "version": COMMERCIAL_TIER_VERSION,
                "entitlements": runtime_rows,
            }
        )
        assert runtime_rows == migration_rows
        assert runtime_hash == expected_hashes[plan_code]
        assert migration._stable_hash(
            {
                "tier_code": plan_code,
                "version": migration._TIER_VERSION,
                "entitlements": migration_rows,
            }
        ) == expected_hashes[plan_code]
        assert migration._PROFILE_DEFINITIONS[plan_code]["id"] == definition.profile_id


def test_migration_keeps_v1_pointers_and_materializes_observed_allowances() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        tables = _create_legacy_tables(connection)
        legacy_profile_ids = _seed_legacy_profiles(connection, tables, migration)
        plans = {
            "org-standard": "standard",
            "org-pro": "pro",
            "org-enterprise": "enterprise",
            "org-internal": "internal_anchor",
        }
        connection.execute(
            tables["organizations"].insert(),
            [
                {
                    "id": organization_id,
                    "plan_type": plan,
                    "tier_profile_id": legacy_profile_ids[
                        "standard" if plan == "pro" else plan
                    ],
                    "tier_version": 1,
                }
                for organization_id, plan in plans.items()
            ],
        )
        connection.execute(
            tables["entitlements"].insert().values(
                id="legacy-custom-entitlement",
                organization_id="org-standard",
                code="limit.crawl.pages_monthly",
                value_type="integer",
                limit_value=37,
                reset_period="month",
                is_enforced=True,
                config_json={"operator_override": True},
                deterministic_hash="legacy-custom-hash",
            )
        )
        connection.execute(
            tables["usage_ledgers"].insert().values(
                id="legacy-usage",
                organization_id="org-standard",
                entitlement_code="limit.crawl.pages_monthly",
                usage_value=19,
            )
        )

        _run_upgrade(connection, migration)

        organizations = {
            row.id: row
            for row in connection.execute(
                sa.select(tables["organizations"])
            ).mappings()
        }
        assert organizations["org-standard"].plan_type == "standard"
        assert organizations["org-pro"].plan_type == "pro"
        assert organizations["org-enterprise"].plan_type == "enterprise"
        assert organizations["org-internal"].plan_type == "internal_anchor"
        assert organizations["org-standard"].tier_profile_id == legacy_profile_ids["standard"]
        assert organizations["org-pro"].tier_profile_id == legacy_profile_ids["standard"]
        assert organizations["org-enterprise"].tier_profile_id == legacy_profile_ids["enterprise"]
        assert organizations["org-internal"].tier_profile_id == legacy_profile_ids["internal_anchor"]
        assert {row.tier_version for row in organizations.values()} == {1}
        expected_limits = {
            "org-standard": 1,
            "org-pro": 10,
            "org-enterprise": 20,
            "org-internal": 20,
        }
        for organization_id, expected_limit in expected_limits.items():
            row = connection.execute(
                sa.select(tables["entitlements"]).where(
                    tables["entitlements"].c.organization_id == organization_id,
                    tables["entitlements"].c.code == "limit.active_locations",
                )
            ).mappings().one()
            assert row.limit_value == expected_limit
            assert row.value_type == "integer"
            assert row.reset_period == "none"
            assert row.is_enforced is True
            assert (
                connection.execute(
                    sa.select(sa.func.count())
                    .select_from(tables["entitlements"])
                    .where(tables["entitlements"].c.organization_id == organization_id)
                ).scalar_one()
                == 10
            )
        legacy = connection.execute(
            sa.select(tables["entitlements"]).where(
                tables["entitlements"].c.id == "legacy-custom-entitlement"
            )
        ).mappings().one()
        assert legacy.limit_value == 37
        assert legacy.reset_period == "month"
        assert legacy.config_json == {"operator_override": True}
        assert legacy.deterministic_hash == "legacy-custom-hash"
        assert connection.execute(
            sa.select(tables["usage_ledgers"].c.usage_value).where(
                tables["usage_ledgers"].c.id == "legacy-usage"
            )
        ).scalar_one() == 19
        activation = connection.execute(
            sa.text(
                "SELECT code, state, catalog_version "
                "FROM commercial_feature_activations"
            )
        ).mappings().one()
        assert activation == {
            "code": "active_location_allowance",
            "state": "observe",
            "catalog_version": migration._CATALOG_VERSION,
        }
        migration_checks = {
            row["name"]
            for row in sa.inspect(connection).get_check_constraints(
                "commercial_feature_activations"
            )
        }
        model_checks = {
            constraint.name
            for constraint in CommercialFeatureActivation.__table__.constraints
            if isinstance(constraint, sa.CheckConstraint)
        }
        assert "ck_commercial_feature_activations_state" in migration_checks
        assert migration_checks == model_checks


def test_downgrade_removes_only_activation_switch_and_preserves_bridge_data() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        tables = _create_legacy_tables(connection)
        legacy_profile_ids = _seed_legacy_profiles(connection, tables, migration)
        plans = {
            "org-standard": "standard",
            "org-pro": "pro",
            "org-enterprise": "enterprise",
            "org-internal": "internal_anchor",
        }
        connection.execute(
            tables["organizations"].insert(),
            [
                {
                    "id": organization_id,
                    "plan_type": plan,
                    "tier_profile_id": legacy_profile_ids[
                        "standard" if plan == "pro" else plan
                    ],
                    "tier_version": 1,
                }
                for organization_id, plan in plans.items()
            ],
        )
        connection.execute(
            tables["entitlements"].insert().values(
                id="legacy-custom-entitlement",
                organization_id="org-standard",
                code="limit.crawl.pages_monthly",
                value_type="integer",
                limit_value=37,
                reset_period="month",
                is_enforced=True,
                config_json={"operator_override": True},
                deterministic_hash="legacy-custom-hash",
            )
        )
        connection.execute(
            tables["usage_ledgers"].insert().values(
                id="legacy-usage",
                organization_id="org-standard",
                entitlement_code="limit.crawl.pages_monthly",
                usage_value=19,
            )
        )

        before_upgrade = {
            row.id: dict(row)
            for row in connection.execute(
                sa.select(tables["organizations"])
            ).mappings()
        }
        _run_upgrade(connection, migration)
        after_upgrade = {
            row.id: dict(row)
            for row in connection.execute(
                sa.select(tables["organizations"])
            ).mappings()
        }
        assert after_upgrade == before_upgrade
        _run_downgrade(connection, migration)
        assert not sa.inspect(connection).has_table("commercial_feature_activations")

        organizations = {
            row.id: row
            for row in connection.execute(
                sa.select(tables["organizations"])
            ).mappings()
        }
        assert {key: dict(value) for key, value in organizations.items()} == before_upgrade
        assert organizations["org-standard"].plan_type == "standard"
        assert organizations["org-standard"].tier_profile_id == legacy_profile_ids["standard"]
        assert organizations["org-pro"].plan_type == "pro"
        assert organizations["org-pro"].tier_profile_id == legacy_profile_ids["standard"]
        assert organizations["org-enterprise"].plan_type == "enterprise"
        assert (
            organizations["org-enterprise"].tier_profile_id
            == legacy_profile_ids["enterprise"]
        )
        assert organizations["org-internal"].plan_type == "internal_anchor"
        assert (
            organizations["org-internal"].tier_profile_id
            == legacy_profile_ids["internal_anchor"]
        )
        assert {row.tier_version for row in organizations.values()} == {1}

        # The database remains forward-migratable: v2 catalog rows and all
        # materialized entitlements survive, while old runtime pointers see
        # only immutable v1 templates that predate active-location capacity.
        assert connection.execute(
            sa.select(sa.func.count()).select_from(tables["tier_profiles"])
        ).scalar_one() == 7
        v1_templates = connection.execute(
            sa.select(tables["tier_profiles"].c.entitlement_template_json).where(
                tables["tier_profiles"].c.version == 1
            )
        ).scalars().all()
        assert len(v1_templates) == 3
        assert all(
            {row["code"] for row in template["entitlements"]}
            == set(migration._LEGACY_ENTITLEMENT_CODES)
            for template in v1_templates
        )
        assert all(
            "limit.active_locations"
            not in {row["code"] for row in template["entitlements"]}
            for template in v1_templates
        )
        assert connection.execute(
            sa.select(sa.func.count()).select_from(tables["entitlements"])
        ).scalar_one() == 40
        legacy = connection.execute(
            sa.select(tables["entitlements"]).where(
                tables["entitlements"].c.id == "legacy-custom-entitlement"
            )
        ).mappings().one()
        assert legacy.limit_value == 37
        assert legacy.config_json == {"operator_override": True}
        assert legacy.deterministic_hash == "legacy-custom-hash"
        assert connection.execute(
            sa.select(tables["usage_ledgers"].c.usage_value).where(
                tables["usage_ledgers"].c.id == "legacy-usage"
            )
        ).scalar_one() == 19


def test_unknown_plan_fails_preflight_without_mutation() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        tables = _create_legacy_tables(connection)
        connection.execute(
            tables["organizations"].insert().values(
                id="org-custom", plan_type="custom_contract", tier_version=9
            )
        )

        with pytest.raises(RuntimeError, match="unsupported organization plan_type"):
            _run_upgrade(connection, migration)

        assert connection.execute(
            sa.select(sa.func.count()).select_from(tables["tier_profiles"])
        ).scalar_one() == 0
        assert connection.execute(
            sa.select(sa.func.count()).select_from(tables["entitlements"])
        ).scalar_one() == 0
        organization = connection.execute(
            sa.select(tables["organizations"])
        ).mappings().one()
        assert organization.plan_type == "custom_contract"
        assert organization.tier_version == 9


@pytest.mark.parametrize("invalid_case", ["inactive", "mutated_template", "wrong_id"])
def test_invalid_existing_canonical_profile_fails_before_other_profiles_are_inserted(
    invalid_case: str,
) -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        tables = _create_legacy_tables(connection)
        legacy_profile_ids = _seed_legacy_profiles(connection, tables, migration)
        rows = migration._template("solo")
        expected_hash = migration._stable_hash(
            {
                "tier_code": "solo",
                "version": migration._TIER_VERSION,
                "entitlements": rows,
            }
        )
        saved_rows = [dict(item) for item in rows]
        if invalid_case == "mutated_template":
            saved_rows[-1] = {**saved_rows[-1], "limit_value": 999}
        connection.execute(
            tables["tier_profiles"].insert().values(
                id=(
                    "wrong-canonical-profile-id"
                    if invalid_case == "wrong_id"
                    else migration._PROFILE_DEFINITIONS["solo"]["id"]
                ),
                tier_code="solo",
                display_name="Solo",
                version=migration._TIER_VERSION,
                entitlement_template_json={"entitlements": saved_rows},
                deterministic_hash=expected_hash,
                is_active=invalid_case != "inactive",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        connection.execute(
            tables["organizations"].insert().values(
                id="org-standard",
                plan_type="standard",
                tier_profile_id=legacy_profile_ids["standard"],
                tier_version=1,
            )
        )

        with pytest.raises(RuntimeError, match="profile preflight failed"):
            _run_upgrade(connection, migration)

        assert connection.execute(
            sa.select(sa.func.count()).select_from(tables["tier_profiles"])
        ).scalar_one() == 4
        assert connection.execute(
            sa.select(sa.func.count()).select_from(tables["entitlements"])
        ).scalar_one() == 0
        organization = connection.execute(
            sa.select(tables["organizations"])
        ).mappings().one()
        assert organization.plan_type == "standard"
        assert organization.tier_profile_id == legacy_profile_ids["standard"]
