-- Terminal-state immutability and governed override (PostgreSQL)
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

ALTER TABLE strategy_recommendations
    ADD COLUMN IF NOT EXISTS engine_version VARCHAR(64),
    ADD COLUMN IF NOT EXISTS threshold_bundle_version VARCHAR(64),
    ADD COLUMN IF NOT EXISTS registry_version VARCHAR(64),
    ADD COLUMN IF NOT EXISTS signal_schema_version VARCHAR(64),
    ADD COLUMN IF NOT EXISTS input_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS output_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS build_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128);

ALTER TABLE strategy_recommendations
    ALTER COLUMN status TYPE strategy_recommendation_status
    USING status::strategy_recommendation_status;

CREATE UNIQUE INDEX IF NOT EXISTS uq_strategy_recommendations_idempotency
ON strategy_recommendations (tenant_id, campaign_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE OR REPLACE FUNCTION enforce_strategy_output_immutability()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN ('EXECUTED', 'FAILED', 'ROLLED_BACK', 'ARCHIVED')
       AND current_setting('app.strategy_override', true) IS DISTINCT FROM 'on' THEN
        RAISE EXCEPTION 'Immutable terminal strategy output record: %', OLD.id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_strategy_output_immutability ON strategy_recommendations;
CREATE TRIGGER trg_strategy_output_immutability
BEFORE UPDATE ON strategy_recommendations
FOR EACH ROW
EXECUTE FUNCTION enforce_strategy_output_immutability();

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

    SELECT * INTO v_old FROM strategy_recommendations WHERE id = p_recommendation_id FOR UPDATE;
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

    INSERT INTO audit_logs (id, tenant_id, actor_user_id, event_type, payload_json, created_at)
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
