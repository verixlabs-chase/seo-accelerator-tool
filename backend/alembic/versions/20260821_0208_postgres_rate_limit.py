"""add a least-privilege PostgreSQL request rate-limit store

Revision ID: 20260821_0208
Revises: 20260820_0207
Create Date: 2026-08-21 15:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260821_0208"
down_revision = "20260820_0207"
branch_labels = None
depends_on = None

TABLE = "request_rate_limit_counters"
CONSUME_FUNCTION = "consume_request_rate_limit"
PRUNE_FUNCTION = "prune_request_rate_limit_counters"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("scope_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_key", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.BigInteger(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(scope_hash) = 64",
            name="ck_request_rate_limit_scope_hash_length",
        ),
        sa.CheckConstraint(
            "length(policy_key) between 1 and 64",
            name="ck_request_rate_limit_policy_key_length",
        ),
        sa.CheckConstraint(
            "request_count between 1 and 1000001",
            name="ck_request_rate_limit_request_count",
        ),
        sa.PrimaryKeyConstraint(
            "scope_hash",
            "policy_key",
            name="pk_request_rate_limit_counters",
        ),
    )
    op.create_index(
        "ix_request_rate_limit_counters_last_seen_at",
        TABLE,
        ["last_seen_at"],
        unique=False,
    )

    if op.get_bind().dialect.name != "postgresql":
        return

    _secure_table()
    _create_consume_function()
    _create_prune_function()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                f"DROP FUNCTION IF EXISTS public.{PRUNE_FUNCTION}(integer, integer)"
            )
        )
        op.execute(
            sa.text(
                f"DROP FUNCTION IF EXISTS public.{CONSUME_FUNCTION}(text, text, integer)"
            )
        )
    op.drop_index(
        "ix_request_rate_limit_counters_last_seen_at",
        table_name=TABLE,
    )
    op.drop_table(TABLE)


def _secure_table() -> None:
    # Migration 0077 grants lsos_app DML on future public tables by default.
    # Rate-limit state is deliberately reachable only through the two narrow
    # SECURITY DEFINER functions below.
    op.execute(
        sa.text(
            f"REVOKE ALL PRIVILEGES ON TABLE public.{TABLE} FROM PUBLIC, lsos_app"
        )
    )
    op.execute(sa.text(f"ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY"))
    # MAINTAIN was added after older supported PostgreSQL releases. Keep it
    # revoked when the server understands it without making migrations on an
    # older database fail at parse time.
    op.execute(
        sa.text(
            f"""
            DO $rate_limit_acl$
            BEGIN
                IF current_setting('server_version_num')::integer >= 170000 THEN
                    EXECUTE 'REVOKE MAINTAIN ON TABLE public.{TABLE} FROM PUBLIC, lsos_app';
                END IF;
            END
            $rate_limit_acl$;
            """
        )
    )


def _create_consume_function() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{CONSUME_FUNCTION}(
                p_scope_hash text,
                p_policy_key text,
                p_request_limit integer
            )
            RETURNS TABLE (
                allowed boolean,
                request_count bigint,
                remaining integer,
                window_started_at timestamp with time zone,
                reset_at timestamp with time zone,
                retry_after_seconds integer
            )
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, public, pg_temp
            SET statement_timeout = '750ms'
            SET lock_timeout = '250ms'
            AS $rate_limit_consume$
            DECLARE
                v_now timestamp with time zone;
                v_current_window timestamp with time zone;
                v_stored_window timestamp with time zone;
                v_count bigint;
                v_previous_count bigint;
                v_window_rolled boolean;
                v_reset_at timestamp with time zone;
                v_retry_after integer;
            BEGIN
                IF p_scope_hash IS NULL
                   OR pg_catalog.length(p_scope_hash) <> 64
                   OR p_scope_hash !~ '^[0-9a-f]{{64}}$' THEN
                    RAISE EXCEPTION 'scope_hash must be 64 lowercase hexadecimal characters'
                        USING ERRCODE = '22023';
                END IF;
                IF p_policy_key IS NULL
                   OR pg_catalog.length(p_policy_key) NOT BETWEEN 1 AND 64
                   OR p_policy_key !~ '^[a-z0-9][a-z0-9_.:-]*$' THEN
                    RAISE EXCEPTION 'policy_key contains unsupported characters'
                        USING ERRCODE = '22023';
                END IF;
                IF p_request_limit IS NULL
                   OR p_request_limit NOT BETWEEN 1 AND 1000000 THEN
                    RAISE EXCEPTION 'request_limit must be between 1 and 1000000'
                        USING ERRCODE = '22023';
                END IF;

                LOOP
                    v_now := pg_catalog.clock_timestamp();
                    v_current_window := pg_catalog.date_trunc('minute', v_now);

                    INSERT INTO public.{TABLE} AS counters (
                        scope_hash,
                        policy_key,
                        window_started_at,
                        request_count,
                        last_seen_at
                    )
                    VALUES (
                        p_scope_hash,
                        p_policy_key,
                        v_current_window,
                        1,
                        v_now
                    )
                    ON CONFLICT (scope_hash, policy_key) DO NOTHING
                    RETURNING counters.window_started_at, counters.request_count
                    INTO v_stored_window, v_count;

                    IF FOUND THEN
                        -- ON CONFLICT may wait on an uncommitted tuple. Sample
                        -- database time again so a wait across a minute boundary
                        -- cannot create a stale new bucket and an extra winner.
                        v_now := pg_catalog.clock_timestamp();
                        v_current_window := pg_catalog.date_trunc('minute', v_now);
                        IF v_stored_window < v_current_window THEN
                            v_stored_window := v_current_window;
                            UPDATE public.{TABLE} AS counters
                            SET window_started_at = v_stored_window,
                                request_count = 1,
                                last_seen_at = v_now
                            WHERE counters.scope_hash = p_scope_hash
                              AND counters.policy_key = p_policy_key;
                        END IF;

                        -- Couple one bounded stale eviction to each net-new
                        -- identity. This prevents cleanup backlog from growing
                        -- indefinitely when a scheduled run is delayed.
                        WITH stale AS (
                            SELECT counters.scope_hash, counters.policy_key
                            FROM public.{TABLE} AS counters
                            WHERE counters.last_seen_at < (
                                v_now - pg_catalog.make_interval(days => 2)
                            )
                              AND NOT (
                                  counters.scope_hash = p_scope_hash
                                  AND counters.policy_key = p_policy_key
                              )
                            ORDER BY counters.last_seen_at
                            LIMIT 1
                            FOR UPDATE SKIP LOCKED
                        )
                        DELETE FROM public.{TABLE} AS counters
                        USING stale
                        WHERE counters.scope_hash = stale.scope_hash
                          AND counters.policy_key = stale.policy_key;
                        EXIT;
                    END IF;

                    SELECT counters.window_started_at, counters.request_count
                    INTO v_stored_window, v_count
                    FROM public.{TABLE} AS counters
                    WHERE counters.scope_hash = p_scope_hash
                      AND counters.policy_key = p_policy_key
                    FOR UPDATE;

                    -- A bounded cleanup may delete an expired row between the
                    -- failed insert and this lock attempt. Retry the insert in
                    -- that rare case rather than returning an ambiguous result.
                    IF NOT FOUND THEN
                        CONTINUE;
                    END IF;

                    -- Take database time only after acquiring the row lock. A
                    -- request that waited across the minute boundary must never
                    -- move a newer counter window backward.
                    v_now := pg_catalog.clock_timestamp();
                    v_current_window := pg_catalog.date_trunc('minute', v_now);
                    v_previous_count := v_count;
                    v_window_rolled := false;
                    IF v_stored_window < v_current_window THEN
                        v_stored_window := v_current_window;
                        v_count := 1;
                        v_window_rolled := true;
                    ELSE
                        -- If the database clock moves backward, retain the
                        -- later stored window. Resetting it backward would hand
                        -- out a second allowance for the same fixed window.
                        v_count := least(
                            v_count + 1,
                            p_request_limit::bigint + 1
                        );
                    END IF;

                    IF v_window_rolled THEN
                        UPDATE public.{TABLE} AS counters
                        SET window_started_at = v_stored_window,
                            request_count = v_count,
                            last_seen_at = v_now
                        WHERE counters.scope_hash = p_scope_hash
                          AND counters.policy_key = p_policy_key;
                    ELSIF v_count > v_previous_count THEN
                        -- request_count is not indexed, so increments remain
                        -- HOT-eligible. Saturated denials do not write at all.
                        UPDATE public.{TABLE} AS counters
                        SET request_count = v_count
                        WHERE counters.scope_hash = p_scope_hash
                          AND counters.policy_key = p_policy_key;
                    END IF;
                    EXIT;
                END LOOP;

                IF v_stored_window < v_now - pg_catalog.make_interval(mins => 1) THEN
                    RAISE EXCEPTION 'rate-limit window is outside the active fixed window'
                        USING ERRCODE = '22000';
                END IF;

                v_reset_at := v_stored_window + pg_catalog.make_interval(mins => 1);
                v_retry_after := greatest(
                    1,
                    pg_catalog.ceil(
                        extract(epoch FROM (v_reset_at - v_now))
                    )::integer
                );

                RETURN QUERY SELECT
                    v_count <= p_request_limit::bigint,
                    v_count,
                    greatest(
                        0::bigint,
                        p_request_limit::bigint - v_count
                    )::integer,
                    v_stored_window,
                    v_reset_at,
                    v_retry_after;
            END
            $rate_limit_consume$;
            """
        )
    )
    op.execute(
        sa.text(
            f"REVOKE ALL PRIVILEGES ON FUNCTION "
            f"public.{CONSUME_FUNCTION}(text, text, integer) FROM PUBLIC"
        )
    )
    op.execute(
        sa.text(
            f"GRANT EXECUTE ON FUNCTION "
            f"public.{CONSUME_FUNCTION}(text, text, integer) TO lsos_app"
        )
    )


def _create_prune_function() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{PRUNE_FUNCTION}(
                p_retention_seconds integer DEFAULT 86400,
                p_batch_size integer DEFAULT 1000
            )
            RETURNS integer
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, public, pg_temp
            SET statement_timeout = '2s'
            SET lock_timeout = '500ms'
            AS $rate_limit_prune$
            DECLARE
                v_deleted integer;
            BEGIN
                IF p_retention_seconds IS NULL
                   OR p_retention_seconds NOT BETWEEN 60 AND 2592000 THEN
                    RAISE EXCEPTION 'retention_seconds must be between 60 and 2592000'
                        USING ERRCODE = '22023';
                END IF;
                IF p_batch_size IS NULL OR p_batch_size NOT BETWEEN 1 AND 10000 THEN
                    RAISE EXCEPTION 'batch_size must be between 1 and 10000'
                        USING ERRCODE = '22023';
                END IF;

                WITH expired AS (
                    SELECT counters.scope_hash, counters.policy_key
                    FROM public.{TABLE} AS counters
                    WHERE counters.last_seen_at < (
                        pg_catalog.clock_timestamp()
                        - pg_catalog.make_interval(secs => p_retention_seconds)
                    )
                    ORDER BY counters.last_seen_at
                    LIMIT p_batch_size
                    FOR UPDATE SKIP LOCKED
                ), deleted AS (
                    DELETE FROM public.{TABLE} AS counters
                    USING expired
                    WHERE counters.scope_hash = expired.scope_hash
                      AND counters.policy_key = expired.policy_key
                    RETURNING 1
                )
                SELECT pg_catalog.count(*)::integer
                INTO v_deleted
                FROM deleted;

                RETURN v_deleted;
            END
            $rate_limit_prune$;
            """
        )
    )
    op.execute(
        sa.text(
            f"REVOKE ALL PRIVILEGES ON FUNCTION "
            f"public.{PRUNE_FUNCTION}(integer, integer) FROM PUBLIC"
        )
    )
    op.execute(
        sa.text(
            f"GRANT EXECUTE ON FUNCTION "
            f"public.{PRUNE_FUNCTION}(integer, integer) TO lsos_app"
        )
    )
