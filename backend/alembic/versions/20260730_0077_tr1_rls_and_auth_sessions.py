"""add database-enforced tenant isolation and revocable auth sessions

Revision ID: 20260730_0077
Revises: 20260729_0076
Create Date: 2026-07-30 11:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260730_0077"
down_revision = "20260729_0076"
branch_labels = None
depends_on = None


_RLS_ROLE = "lsos_app"
_RLS_POLICY = "lsos_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("refresh_jti", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refresh_jti"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"], unique=False)
    op.create_index(
        "ix_auth_sessions_organization_id",
        "auth_sessions",
        ["organization_id"],
        unique=False,
    )
    op.create_index("ix_auth_sessions_status", "auth_sessions", ["status"], unique=False)
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"], unique=False)
    op.create_index(
        "ix_auth_sessions_user_status",
        "auth_sessions",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_auth_sessions_organization_status",
        "auth_sessions",
        ["organization_id", "status"],
        unique=False,
    )

    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_RLS_ROLE}') THEN
                    CREATE ROLE {_RLS_ROLE}
                        NOLOGIN
                        NOSUPERUSER
                        NOCREATEDB
                        NOCREATEROLE
                        NOREPLICATION;
                END IF;
                EXECUTE format('GRANT {_RLS_ROLE} TO %I', current_user);
            END
            $$;

            GRANT USAGE ON SCHEMA public TO {_RLS_ROLE};
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {_RLS_ROLE};
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {_RLS_ROLE};
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
                GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {_RLS_ROLE};
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
                GRANT USAGE, SELECT ON SEQUENCES TO {_RLS_ROLE};
            """
        )
    )

    op.execute(
        sa.text(
            f"""
            DO $$
            DECLARE
                scoped_table record;
                policy_expression text;
            BEGIN
                FOR scoped_table IN
                    SELECT
                        columns.table_name,
                        bool_or(columns.column_name = 'tenant_id') AS has_tenant_id,
                        bool_or(columns.column_name = 'organization_id') AS has_organization_id
                    FROM information_schema.columns AS columns
                    JOIN information_schema.tables AS tables
                      ON tables.table_schema = columns.table_schema
                     AND tables.table_name = columns.table_name
                     AND tables.table_type = 'BASE TABLE'
                    WHERE columns.table_schema = 'public'
                    GROUP BY columns.table_name
                    HAVING bool_or(columns.column_name = 'tenant_id')
                        OR bool_or(columns.column_name = 'organization_id')
                LOOP
                    IF scoped_table.has_tenant_id AND scoped_table.has_organization_id THEN
                        policy_expression :=
                            '(current_setting(''app.platform_access'', true) = ''on'' OR '
                            || '(tenant_id::text = current_setting(''app.current_tenant_id'', true) '
                            || 'AND (organization_id IS NULL OR organization_id::text = '
                            || 'current_setting(''app.current_organization_id'', true))))';
                    ELSIF scoped_table.has_organization_id THEN
                        policy_expression :=
                            '(current_setting(''app.platform_access'', true) = ''on'' OR '
                            || 'organization_id::text = '
                            || 'current_setting(''app.current_organization_id'', true))';
                    ELSE
                        policy_expression :=
                            '(current_setting(''app.platform_access'', true) = ''on'' OR '
                            || 'tenant_id::text = '
                            || 'current_setting(''app.current_tenant_id'', true))';
                    END IF;

                    EXECUTE format(
                        'ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',
                        scoped_table.table_name
                    );
                    EXECUTE format(
                        'DROP POLICY IF EXISTS {_RLS_POLICY} ON public.%I',
                        scoped_table.table_name
                    );
                    EXECUTE format(
                        'CREATE POLICY {_RLS_POLICY} ON public.%I '
                        || 'FOR ALL TO {_RLS_ROLE} USING (%s) WITH CHECK (%s)',
                        scoped_table.table_name,
                        policy_expression,
                        policy_expression
                    );
                END LOOP;

                ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS {_RLS_POLICY} ON public.organizations;
                CREATE POLICY {_RLS_POLICY} ON public.organizations
                    FOR ALL TO {_RLS_ROLE}
                    USING (
                        current_setting('app.platform_access', true) = 'on'
                        OR id::text = current_setting('app.current_organization_id', true)
                    )
                    WITH CHECK (
                        current_setting('app.platform_access', true) = 'on'
                        OR id::text = current_setting('app.current_organization_id', true)
                    );

                ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS {_RLS_POLICY} ON public.tenants;
                CREATE POLICY {_RLS_POLICY} ON public.tenants
                    FOR ALL TO {_RLS_ROLE}
                    USING (
                        current_setting('app.platform_access', true) = 'on'
                        OR id::text = current_setting('app.current_tenant_id', true)
                    )
                    WITH CHECK (
                        current_setting('app.platform_access', true) = 'on'
                        OR id::text = current_setting('app.current_tenant_id', true)
                    );
            END
            $$;
            """
        )
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                f"""
                DO $$
                DECLARE
                    scoped_table record;
                BEGIN
                    FOR scoped_table IN
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
                    LOOP
                        EXECUTE format(
                            'DROP POLICY IF EXISTS {_RLS_POLICY} ON public.%I',
                            scoped_table.table_name
                        );
                        EXECUTE format(
                            'ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY',
                            scoped_table.table_name
                        );
                    END LOOP;

                    REVOKE SELECT, INSERT, UPDATE, DELETE
                        ON ALL TABLES IN SCHEMA public FROM {_RLS_ROLE};
                    REVOKE USAGE, SELECT
                        ON ALL SEQUENCES IN SCHEMA public FROM {_RLS_ROLE};
                    REVOKE USAGE ON SCHEMA public FROM {_RLS_ROLE};
                    ALTER DEFAULT PRIVILEGES IN SCHEMA public
                        REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {_RLS_ROLE};
                    ALTER DEFAULT PRIVILEGES IN SCHEMA public
                        REVOKE USAGE, SELECT ON SEQUENCES FROM {_RLS_ROLE};
                    EXECUTE format('REVOKE {_RLS_ROLE} FROM %I', current_user);
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_RLS_ROLE}') THEN
                        DROP ROLE {_RLS_ROLE};
                    END IF;
                END
                $$;
                """
            )
        )

    op.drop_index("ix_auth_sessions_organization_status", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_status", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_status", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_organization_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
