from __future__ import annotations

import argparse
import json
import os
from typing import Any

from sqlalchemy import create_engine, inspect, text


DEFAULT_SCHEMA_HEAD = "20260730_0077"


def _scalar(connection, statement: str) -> int:  # noqa: ANN001
    return int(connection.execute(text(statement)).scalar_one())


def verify_restore(database_url: str, *, expected_schema: str) -> dict[str, Any]:
    engine = create_engine(database_url, pool_pre_ping=True)
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
    args = parser.parse_args()

    database_url = os.getenv(args.dsn_env, "").strip()
    if not database_url:
        raise SystemExit(f"{args.dsn_env} is required; keep database credentials out of command history.")

    result = verify_restore(database_url, expected_schema=args.expected_schema)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
