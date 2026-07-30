from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from app.db.session import _normalize_postgres_dsn


DEFAULT_SCHEMA_HEAD = "20260730_0077"


def _scalar(connection, statement: str) -> int:  # noqa: ANN001
    return int(connection.execute(text(statement)).scalar_one())


def _rls_behavior_probe(connection) -> dict[str, Any]:  # noqa: ANN001
    source = (
        connection.execute(
            text(
                """
                SELECT
                    organization.id AS organization_id,
                    tenant.id AS tenant_id,
                    organization.tier_profile_id,
                    organization.tier_version
                FROM organizations AS organization
                JOIN tenants AS tenant ON tenant.id = organization.id
                ORDER BY organization.created_at ASC
                LIMIT 1
                """
            )
        )
        .mappings()
        .first()
    )
    if source is None:
        return {
            "passed": False,
            "reason": "no_linked_tenant_organization_available",
            "persisted_rows": False,
        }

    suffix = uuid.uuid4().hex
    tenant_a = str(source["tenant_id"])
    organization_a = str(source["organization_id"])
    tenant_b = str(uuid.uuid4())
    organization_b = tenant_b
    campaign_a = str(uuid.uuid4())
    campaign_b = str(uuid.uuid4())
    cross_insert = str(uuid.uuid4())
    probe = connection.begin_nested()
    cross_insert_blocked = False
    visible_campaign_ids: list[str] = []
    cross_update_rowcount = -1
    try:
        connection.execute(
            text(
                """
                INSERT INTO tenants (id, name, status, created_at)
                VALUES (:id, :name, 'Active', CURRENT_TIMESTAMP)
                """
            ),
            {"id": tenant_b, "name": f"TR1 restore probe tenant {suffix}"},
        )
        connection.execute(
            text(
                """
                INSERT INTO organizations (
                    id,
                    name,
                    plan_type,
                    billing_mode,
                    status,
                    tier_profile_id,
                    tier_version,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :name,
                    'standard',
                    'subscription',
                    'active',
                    :tier_profile_id,
                    :tier_version,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": organization_b,
                "name": f"TR1 restore probe org {suffix}",
                "tier_profile_id": str(source["tier_profile_id"]),
                "tier_version": int(source["tier_version"]),
            },
        )
        for campaign_id, tenant_id, organization_id, marker in (
            (campaign_a, tenant_a, organization_a, "a"),
            (campaign_b, tenant_b, organization_b, "b"),
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO campaigns (
                        id,
                        tenant_id,
                        organization_id,
                        name,
                        domain,
                        month_number,
                        setup_state,
                        manual_automation_lock,
                        created_at
                    )
                    VALUES (
                        :id,
                        :tenant_id,
                        :organization_id,
                        :name,
                        :domain,
                        1,
                        'Draft',
                        false,
                        CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": campaign_id,
                    "tenant_id": tenant_id,
                    "organization_id": organization_id,
                    "name": f"TR1 restore probe campaign {marker} {suffix}",
                    "domain": f"tr1-{marker}-{suffix}.invalid",
                },
            )

        connection.exec_driver_sql("SET LOCAL ROLE lsos_app")
        connection.execute(
            text(
                """
                SELECT
                    set_config('app.current_tenant_id', :tenant_id, true),
                    set_config('app.current_organization_id', :organization_id, true),
                    set_config('app.current_user_id', :user_id, true),
                    set_config('app.platform_access', 'off', true)
                """
            ),
            {
                "tenant_id": tenant_a,
                "organization_id": organization_a,
                "user_id": str(uuid.uuid4()),
            },
        )
        visible_campaign_ids = list(
            connection.execute(
                text(
                    """
                    SELECT id
                    FROM campaigns
                    WHERE id IN (:campaign_a, :campaign_b)
                    ORDER BY id
                    """
                ),
                {"campaign_a": campaign_a, "campaign_b": campaign_b},
            ).scalars()
        )
        cross_update = connection.execute(
            text(
                """
                UPDATE campaigns
                SET name = name
                WHERE id = :campaign_b
                """
            ),
            {"campaign_b": campaign_b},
        )
        cross_update_rowcount = int(cross_update.rowcount or 0)

        cross_write = connection.begin_nested()
        try:
            connection.execute(
                text(
                    """
                    INSERT INTO campaigns (
                        id,
                        tenant_id,
                        organization_id,
                        name,
                        domain,
                        month_number,
                        setup_state,
                        manual_automation_lock,
                        created_at
                    )
                    VALUES (
                        :id,
                        :tenant_id,
                        :organization_id,
                        :name,
                        :domain,
                        1,
                        'Draft',
                        false,
                        CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": cross_insert,
                    "tenant_id": tenant_b,
                    "organization_id": organization_b,
                    "name": f"TR1 blocked insert {suffix}",
                    "domain": f"tr1-blocked-{suffix}.invalid",
                },
            )
        except DBAPIError:
            cross_insert_blocked = True
        finally:
            cross_write.rollback()
        connection.exec_driver_sql("RESET ROLE")
    finally:
        probe.rollback()

    return {
        "passed": (
            visible_campaign_ids == [campaign_a]
            and cross_update_rowcount == 0
            and cross_insert_blocked
        ),
        "visible_own_campaign": campaign_a in visible_campaign_ids,
        "visible_cross_tenant_campaign": campaign_b in visible_campaign_ids,
        "cross_tenant_update_rows": cross_update_rowcount,
        "cross_tenant_insert_blocked": cross_insert_blocked,
        "persisted_rows": False,
    }


def _load_expected_row_counts(path: str | None) -> dict[str, int] | None:
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    candidate = payload.get("checks", {}).get("row_counts", payload.get("row_counts"))
    if not isinstance(candidate, dict):
        raise ValueError("Baseline JSON must contain row_counts or checks.row_counts.")
    return {str(key): int(value) for key, value in candidate.items()}


def verify_restore(
    database_url: str,
    *,
    expected_schema: str,
    expected_row_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    normalized_database_url = _normalize_postgres_dsn(database_url)
    engine_options: dict[str, Any] = {"pool_pre_ping": True}
    if normalized_database_url.startswith("postgresql"):
        engine_options["connect_args"] = {"prepare_threshold": None}
    engine = create_engine(normalized_database_url, **engine_options)
    checks: dict[str, Any] = {}
    failures: list[str] = []
    try:
        inspector = inspect(engine)
        required_tables = {
            "alembic_version",
            "auth_sessions",
            "business_locations",
            "campaigns",
            "organization_memberships",
            "organizations",
            "platform_jobs",
            "tenants",
            "users",
        }
        missing_tables = sorted(required_tables - set(inspector.get_table_names()))
        checks["missing_required_tables"] = missing_tables
        if missing_tables:
            failures.append("required_tables_missing")
            return {"passed": False, "checks": checks, "failures": failures}

        with engine.begin() as connection:
            schema_head = connection.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar_one_or_none()
            checks["schema_head"] = schema_head
            checks["expected_schema_head"] = expected_schema
            if schema_head != expected_schema:
                failures.append("schema_head_mismatch")

            checks["row_counts"] = {
                "organizations": _scalar(connection, "SELECT count(*) FROM organizations"),
                "users": _scalar(connection, "SELECT count(*) FROM users"),
                "campaigns": _scalar(connection, "SELECT count(*) FROM campaigns"),
                "business_locations": _scalar(
                    connection,
                    "SELECT count(*) FROM business_locations",
                ),
            }
            if expected_row_counts is not None:
                checks["expected_row_counts"] = expected_row_counts
                checks["row_count_deltas"] = {
                    table_name: checks["row_counts"].get(table_name, 0) - expected_count
                    for table_name, expected_count in expected_row_counts.items()
                }
                if any(checks["row_count_deltas"].values()):
                    failures.append("row_count_mismatch")
            checks["orphan_counts"] = {
                "campaign_organization": _scalar(
                    connection,
                    """
                    SELECT count(*)
                    FROM campaigns AS campaign
                    LEFT JOIN organizations AS organization
                      ON organization.id = campaign.organization_id
                    WHERE campaign.organization_id IS NOT NULL
                      AND organization.id IS NULL
                    """,
                ),
                "location_organization": _scalar(
                    connection,
                    """
                    SELECT count(*)
                    FROM business_locations AS location
                    LEFT JOIN organizations AS organization
                      ON organization.id = location.organization_id
                    WHERE organization.id IS NULL
                    """,
                ),
                "membership_user": _scalar(
                    connection,
                    """
                    SELECT count(*)
                    FROM organization_memberships AS membership
                    LEFT JOIN users AS app_user ON app_user.id = membership.user_id
                    WHERE app_user.id IS NULL
                    """,
                ),
                "membership_organization": _scalar(
                    connection,
                    """
                    SELECT count(*)
                    FROM organization_memberships AS membership
                    LEFT JOIN organizations AS organization
                      ON organization.id = membership.organization_id
                    WHERE organization.id IS NULL
                    """,
                ),
            }
            if any(checks["orphan_counts"].values()):
                failures.append("tenant_integrity_orphans_detected")

            if connection.dialect.name == "postgresql":
                missing_rls = (
                    connection.execute(
                        text(
                            """
                            WITH scoped_tables AS (
                                SELECT DISTINCT columns.table_name
                                FROM information_schema.columns AS columns
                                JOIN information_schema.tables AS tables
                                  ON tables.table_schema = columns.table_schema
                                 AND tables.table_name = columns.table_name
                                 AND tables.table_type = 'BASE TABLE'
                                WHERE columns.table_schema = 'public'
                                  AND (
                                      columns.column_name IN ('tenant_id', 'organization_id')
                                      OR columns.table_name IN ('organizations', 'tenants')
                                  )
                            )
                            SELECT scoped_tables.table_name
                            FROM scoped_tables
                            JOIN pg_class
                              ON pg_class.relname = scoped_tables.table_name
                            JOIN pg_namespace
                              ON pg_namespace.oid = pg_class.relnamespace
                             AND pg_namespace.nspname = 'public'
                            WHERE pg_class.relrowsecurity = false
                            ORDER BY scoped_tables.table_name
                            """
                        )
                    )
                    .scalars()
                    .all()
                )
                checks["rls_missing_tables"] = list(missing_rls)
                checks["rls_app_role_exists"] = bool(
                    connection.execute(
                        text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lsos_app')")
                    ).scalar_one()
                )
                if missing_rls or not checks["rls_app_role_exists"]:
                    failures.append("rls_coverage_invalid")
                if not missing_rls and checks["rls_app_role_exists"]:
                    checks["rls_behavior"] = _rls_behavior_probe(connection)
                    if not checks["rls_behavior"]["passed"]:
                        failures.append("rls_behavior_invalid")
            else:
                checks["rls_check"] = "skipped_non_postgresql"
    finally:
        engine.dispose()

    return {"passed": not failures, "checks": checks, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify schema, tenant integrity, and RLS after restoring a database backup."
    )
    parser.add_argument(
        "--dsn-env",
        default="RESTORED_DATABASE_URL",
        help="Environment variable containing the restored database DSN.",
    )
    parser.add_argument("--expected-schema", default=DEFAULT_SCHEMA_HEAD)
    parser.add_argument(
        "--baseline",
        help="Optional JSON evidence file whose row counts must match the restore.",
    )
    parser.add_argument(
        "--output",
        help="Optional path for the JSON evidence. Parent directories are created.",
    )
    args = parser.parse_args()

    database_url = os.getenv(args.dsn_env, "").strip()
    if not database_url:
        raise SystemExit(f"{args.dsn_env} is required; keep database credentials out of command history.")

    result = verify_restore(
        database_url,
        expected_schema=args.expected_schema,
        expected_row_counts=_load_expected_row_counts(args.baseline),
    )
    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
