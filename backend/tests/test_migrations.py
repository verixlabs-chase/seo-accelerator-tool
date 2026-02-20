import os
import shutil
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.settings import get_settings


def test_migration_upgrade_and_downgrade():
    tmp_root = Path(".tmp_test_migrations")
    tmp_root.mkdir(exist_ok=True)
    tmp = tmp_root / str(uuid.uuid4())
    tmp.mkdir(exist_ok=True)
    try:
        db_path = os.path.join(str(tmp.resolve()), "mig.db")
        dsn = f"sqlite:///{db_path}"
        os.environ["DATABASE_URL"] = dsn
        os.environ["POSTGRES_DSN"] = dsn
        get_settings.cache_clear()

        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", dsn)
        cfg.attributes["connection_url"] = dsn

        print(f"[migrations-test] DATABASE_URL={dsn}")
        print(f"[migrations-test] alembic-config-url={cfg.get_main_option('sqlalchemy.url')}")

        command.upgrade(cfg, "head")
        engine = create_engine(dsn)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        with engine.connect() as conn:
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            enterprise_sponsored_org = conn.execute(
                text(
                    "SELECT id, plan_type, billing_mode FROM organizations "
                    "WHERE plan_type='enterprise' AND billing_mode='platform_sponsored' LIMIT 1"
                )
            ).first()
            assert enterprise_sponsored_org is not None
            org_policy = conn.execute(
                text(
                    "SELECT credential_mode FROM provider_policies "
                    "WHERE organization_id=:org_id AND provider_name='dataforseo'"
                ),
                {"org_id": enterprise_sponsored_org[0]},
            ).first()
            assert org_policy is not None
            assert enterprise_sponsored_org[1] == "enterprise"
            assert enterprise_sponsored_org[2] == "platform_sponsored"
            assert org_policy[0] == "byo_required"
        print(f"[migrations-test] alembic_revision={revision}")
        print(f"[migrations-test] table_count={len(tables)}")

        assert "campaigns" in tables, f"campaigns table missing for db={dsn}; tables={tables}"
        assert "task_executions" in inspector.get_table_names()
        assert "crawl_runs" in inspector.get_table_names()
        assert "crawl_frontier_urls" in inspector.get_table_names()
        assert "technical_issues" in inspector.get_table_names()
        assert "keyword_clusters" in inspector.get_table_names()
        assert "campaign_keywords" in inspector.get_table_names()
        assert "rankings" in inspector.get_table_names()
        assert "ranking_snapshots" in inspector.get_table_names()
        assert "competitors" in inspector.get_table_names()
        assert "competitor_rankings" in inspector.get_table_names()
        assert "competitor_pages" in inspector.get_table_names()
        assert "competitor_signals" in inspector.get_table_names()
        assert "content_assets" in inspector.get_table_names()
        assert "editorial_calendar" in inspector.get_table_names()
        assert "internal_link_map" in inspector.get_table_names()
        assert "content_qc_events" in inspector.get_table_names()
        assert "local_profiles" in inspector.get_table_names()
        assert "local_health_snapshots" in inspector.get_table_names()
        assert "reviews" in inspector.get_table_names()
        assert "review_velocity_snapshots" in inspector.get_table_names()
        assert "outreach_campaigns" in inspector.get_table_names()
        assert "outreach_contacts" in inspector.get_table_names()
        assert "backlink_opportunities" in inspector.get_table_names()
        assert "backlinks" in inspector.get_table_names()
        assert "citations" in inspector.get_table_names()
        assert "strategy_recommendations" in inspector.get_table_names()
        assert "intelligence_scores" in inspector.get_table_names()
        assert "campaign_milestones" in inspector.get_table_names()
        assert "anomaly_events" in inspector.get_table_names()
        assert "monthly_reports" in inspector.get_table_names()
        assert "report_artifacts" in inspector.get_table_names()
        assert "report_delivery_events" in inspector.get_table_names()
        assert "report_template_versions" in inspector.get_table_names()
        assert "report_schedules" in inspector.get_table_names()
        assert "reference_library_versions" in inspector.get_table_names()
        assert "reference_library_artifacts" in inspector.get_table_names()
        assert "reference_library_validation_runs" in inspector.get_table_names()
        assert "reference_library_activations" in inspector.get_table_names()
        assert "page_entities" in inspector.get_table_names()
        assert "competitor_entities" in inspector.get_table_names()
        assert "entity_analysis_runs" in inspector.get_table_names()
        assert "provider_health_states" in inspector.get_table_names()
        assert "provider_quota_states" in inspector.get_table_names()
        assert "provider_execution_metrics" in inspector.get_table_names()
        assert "organizations" in inspector.get_table_names()
        assert "provider_policies" in inspector.get_table_names()
        assert "organization_provider_credentials" in inspector.get_table_names()
        assert "platform_provider_credentials" in inspector.get_table_names()
        assert "sub_accounts" in inspector.get_table_names()
        org_cols = {col["name"] for col in inspector.get_columns("organizations")}
        assert "plan_type" in org_cols
        assert "billing_mode" in org_cols
        policy_cols = {col["name"] for col in inspector.get_columns("provider_policies")}
        assert "credential_mode" in policy_cols
        org_cred_cols = {col["name"] for col in inspector.get_columns("organization_provider_credentials")}
        platform_cred_cols = {col["name"] for col in inspector.get_columns("platform_provider_credentials")}
        assert "encrypted_secret_blob" in org_cred_cols
        assert "key_reference" in org_cred_cols
        assert "key_version" in org_cred_cols
        assert "encrypted_secret_blob" in platform_cred_cols
        assert "key_reference" in platform_cred_cols
        assert "key_version" in platform_cred_cols
        sub_account_cols = {col["name"] for col in inspector.get_columns("sub_accounts")}
        assert "organization_id" in sub_account_cols
        assert "name" in sub_account_cols
        assert "status" in sub_account_cols
        campaign_cols = {col["name"] for col in inspector.get_columns("campaigns")}
        report_schedule_cols = {col["name"] for col in inspector.get_columns("report_schedules")}
        metric_cols = {col["name"] for col in inspector.get_columns("provider_execution_metrics")}
        metric_indexes = {idx["name"] for idx in inspector.get_indexes("provider_execution_metrics")}
        assert "sub_account_id" in campaign_cols
        assert "sub_account_id" in report_schedule_cols
        assert "sub_account_id" in metric_cols
        assert "campaign_id" in metric_cols
        assert "ix_provider_execution_metrics_tenant_campaign_created_at" in metric_indexes

        tenant_cols = {col["name"] for col in inspector.get_columns("tenants")}
        assert "status" in tenant_cols
        assert "setup_state" in campaign_cols
        strategy_cols = {col["name"] for col in inspector.get_columns("strategy_recommendations")}
        assert "confidence_score" in strategy_cols
        assert "evidence_json" in strategy_cols
        assert "risk_tier" in strategy_cols
        assert "rollback_plan_json" in strategy_cols

        command.downgrade(cfg, "base")
        inspector2 = inspect(engine)
        assert "campaigns" not in inspector2.get_table_names()
    finally:
        get_settings.cache_clear()
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("POSTGRES_DSN", None)
        shutil.rmtree(tmp, ignore_errors=True)
