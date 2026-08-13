import ast
import os
import shutil
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from app.core.settings import get_settings
from app.db.base import Base


def test_explicit_migration_identifiers_fit_postgres_limit():
    """Keep named constraints and indexes valid on PostgreSQL, not only SQLite."""
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    prefixes = ("pk_", "fk_", "uq_", "ck_", "ix_")
    overlong: list[tuple[str, int, str]] = []

    for migration_path in versions_dir.glob("*.py"):
        tree = ast.parse(migration_path.read_text(encoding="utf-8"), filename=str(migration_path))
        for node in ast.walk(tree):
            value = node.value if isinstance(node, ast.Constant) else None
            if (
                isinstance(value, str)
                and value.startswith(prefixes)
                and value.replace("_", "").isalnum()
                and len(value) > 63
            ):
                overlong.append((migration_path.name, node.lineno, value))

    assert not overlong, f"PostgreSQL identifiers exceed 63 characters: {overlong}"


def test_model_index_identifiers_fit_postgres_limit():
    """Prevent ORM-created indexes from failing only when PostgreSQL creates metadata."""
    overlong = sorted(
        (table.name, index.name, len(index.name))
        for table in Base.metadata.tables.values()
        for index in table.indexes
        if index.name and len(index.name) > 63
    )

    assert not overlong, f"ORM index identifiers exceed 63 characters: {overlong}"


def test_migration_upgrade_and_downgrade():
    tmp = Path(tempfile.mkdtemp(prefix="tmp_test_migrations-"))
    backend_dir = Path(__file__).resolve().parents[1]
    engine = None
    try:
        db_path = tmp / "mig.db"
        dsn = f"sqlite:///{db_path.as_posix()}"
        os.environ["DATABASE_URL"] = dsn
        os.environ["POSTGRES_DSN"] = dsn
        get_settings.cache_clear()

        cfg = Config(str(backend_dir / "alembic.ini"))
        cfg.set_main_option("script_location", str(backend_dir / "alembic"))
        cfg.set_main_option("sqlalchemy.url", dsn)
        cfg.attributes["connection_url"] = dsn

        print(f"[migrations-test] DATABASE_URL={dsn}")
        print(f"[migrations-test] alembic-config-url={cfg.get_main_option('sqlalchemy.url')}")

        command.upgrade(cfg, "head")
        engine = create_engine(
            dsn,
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=NullPool,
        )
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
            tier_profile_count = conn.execute(text("SELECT count(*) FROM tier_profiles")).scalar()
            unprovisioned_org_count = conn.execute(
                text(
                    "SELECT count(*) FROM organizations o "
                    "WHERE o.tier_profile_id IS NULL OR o.tier_version IS NULL "
                    "OR (SELECT count(*) FROM entitlements e WHERE e.organization_id=o.id) < 9"
                )
            ).scalar()
            assert tier_profile_count == 3
            assert unprovisioned_org_count == 0
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
        ranking_snapshot_columns = {
            column["name"] for column in inspector.get_columns("ranking_snapshots")
        }
        assert {
            "source_type",
            "source_system",
            "source_record_id",
            "import_batch_id",
        }.issubset(ranking_snapshot_columns)
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
        assert "directory_listings" in inspector.get_table_names()
        assert "directory_listing_observations" in inspector.get_table_names()
        assert "directory_listing_discovery_runs" in inspector.get_table_names()
        assert "reputation_reviews" in inspector.get_table_names()
        assert "reputation_review_observations" in inspector.get_table_names()
        assert "reputation_response_policies" in inspector.get_table_names()
        assert "reputation_response_drafts" in inspector.get_table_names()
        assert "reputation_provider_capabilities" in inspector.get_table_names()
        assert "reputation_response_executions" in inspector.get_table_names()
        assert "portfolio_location_groups" in inspector.get_table_names()
        assert "portfolio_location_group_members" in inspector.get_table_names()
        assert "portfolio_target_snapshots" in inspector.get_table_names()
        target_snapshot_cols = {
            col["name"] for col in inspector.get_columns("portfolio_target_snapshots")
        }
        assert {
            "location_group_version",
            "selection_json",
            "targets_json",
            "exceptions_json",
            "target_hash",
            "blocked_count",
        }.issubset(target_snapshot_cols)
        assert "strategy_recommendations" in inspector.get_table_names()
        assert "intelligence_scores" in inspector.get_table_names()
        assert "campaign_milestones" in inspector.get_table_names()
        assert "anomaly_events" in inspector.get_table_names()
        assert "monthly_reports" in inspector.get_table_names()
        assert "report_artifacts" in inspector.get_table_names()
        report_artifact_cols = {
            col["name"] for col in inspector.get_columns("report_artifacts")
        }
        assert "content_blob" in report_artifact_cols
        assert "report_delivery_events" in inspector.get_table_names()
        assert "report_template_versions" in inspector.get_table_names()
        assert "report_schedules" in inspector.get_table_names()
        assert "reference_library_versions" in inspector.get_table_names()
        assert "reference_library_artifacts" in inspector.get_table_names()
        assert "reference_library_validation_runs" in inspector.get_table_names()
        assert "reference_library_activations" in inspector.get_table_names()
        assert "standards_source_registry" in inspector.get_table_names()
        assert "standards_source_snapshots" in inspector.get_table_names()
        assert "standards_change_candidates" in inspector.get_table_names()
        assert "standards_impact_links" in inspector.get_table_names()
        assert "provider_metric_contract_versions" in inspector.get_table_names()
        assert "standards_replay_reports" in inspector.get_table_names()
        assert "standards_approvals" in inspector.get_table_names()
        assert "standards_rollouts" in inspector.get_table_names()
        assert "page_entities" in inspector.get_table_names()
        assert "competitor_entities" in inspector.get_table_names()
        assert "entity_analysis_runs" in inspector.get_table_names()
        assert "provider_health_states" in inspector.get_table_names()
        assert "provider_quota_states" in inspector.get_table_names()
        assert "provider_execution_metrics" in inspector.get_table_names()
        assert "portfolio_usage_daily" in inspector.get_table_names()
        assert "platform_jobs" in inspector.get_table_names()
        assert "campaign_daily_metrics" in inspector.get_table_names()
        assert "search_console_daily_metrics" in inspector.get_table_names()
        assert "analytics_daily_metrics" in inspector.get_table_names()
        assert "keyword_daily_economics" in inspector.get_table_names()
        assert "keyword_market_snapshots" in inspector.get_table_names()
        assert "temporal_signal_snapshots" in inspector.get_table_names()
        assert "momentum_metrics" in inspector.get_table_names()
        assert "strategy_phase_history" in inspector.get_table_names()
        assert "strategy_automation_events" in inspector.get_table_names()
        automation_cols = {
            col["name"] for col in inspector.get_columns("strategy_automation_events")
        }
        assert "decision_hash" in automation_cols
        assert "trace_payload" in automation_cols
        assert "organizations" in inspector.get_table_names()
        assert "provider_policies" in inspector.get_table_names()
        assert "organization_provider_credentials" in inspector.get_table_names()
        assert "organization_oauth_clients" in inspector.get_table_names()
        assert "platform_provider_credentials" in inspector.get_table_names()
        assert "sub_accounts" in inspector.get_table_names()
        org_cols = {col["name"] for col in inspector.get_columns("organizations")}
        assert "plan_type" in org_cols
        assert "billing_mode" in org_cols
        policy_cols = {col["name"] for col in inspector.get_columns("provider_policies")}
        assert "credential_mode" in policy_cols
        org_cred_cols = {
            col["name"] for col in inspector.get_columns("organization_provider_credentials")
        }
        org_oauth_client_cols = {
            col["name"] for col in inspector.get_columns("organization_oauth_clients")
        }
        platform_cred_cols = {
            col["name"] for col in inspector.get_columns("platform_provider_credentials")
        }
        assert "encrypted_secret_blob" in org_cred_cols
        assert "key_reference" in org_cred_cols
        assert "key_version" in org_cred_cols
        assert "encrypted_secret_blob" in platform_cred_cols
        assert "key_reference" in platform_cred_cols
        assert "key_version" in platform_cred_cols
        assert "encrypted_secret_blob" in org_oauth_client_cols
        assert "key_reference" in org_oauth_client_cols
        assert "key_version" in org_oauth_client_cols
        sub_account_cols = {col["name"] for col in inspector.get_columns("sub_accounts")}
        assert "organization_id" in sub_account_cols
        assert "name" in sub_account_cols
        assert "status" in sub_account_cols
        campaign_cols = {col["name"] for col in inspector.get_columns("campaigns")}
        business_location_cols = {
            col["name"] for col in inspector.get_columns("business_locations")
        }
        business_location_indexes = {
            idx["name"] for idx in inspector.get_indexes("business_locations")
        }
        campaign_indexes = {idx["name"] for idx in inspector.get_indexes("campaigns")}
        report_schedule_cols = {col["name"] for col in inspector.get_columns("report_schedules")}
        metric_cols = {col["name"] for col in inspector.get_columns("provider_execution_metrics")}
        metric_indexes = {
            idx["name"] for idx in inspector.get_indexes("provider_execution_metrics")
        }
        platform_job_cols = {col["name"] for col in inspector.get_columns("platform_jobs")}
        platform_job_indexes = {idx["name"] for idx in inspector.get_indexes("platform_jobs")}
        campaign_daily_metric_cols = {
            col["name"] for col in inspector.get_columns("campaign_daily_metrics")
        }
        campaign_daily_metric_indexes = {
            idx["name"] for idx in inspector.get_indexes("campaign_daily_metrics")
        }
        search_console_daily_metric_indexes = {
            idx["name"] for idx in inspector.get_indexes("search_console_daily_metrics")
        }
        search_console_daily_metric_cols = {
            col["name"] for col in inspector.get_columns("search_console_daily_metrics")
        }
        provider_metric_contract_cols = {
            col["name"] for col in inspector.get_columns("provider_metric_contract_versions")
        }
        assert {
            "lifecycle_status",
            "supersedes_version_id",
            "standards_change_candidate_id",
            "proposed_by_user_id",
            "proposed_at",
        }.issubset(provider_metric_contract_cols)
        analytics_daily_metric_indexes = {
            idx["name"] for idx in inspector.get_indexes("analytics_daily_metrics")
        }
        keyword_daily_economics_indexes = {
            idx["name"] for idx in inspector.get_indexes("keyword_daily_economics")
        }
        keyword_market_snapshot_indexes = {
            idx["name"] for idx in inspector.get_indexes("keyword_market_snapshots")
        }
        listing_discovery_cols = {
            col["name"] for col in inspector.get_columns("directory_listing_discovery_runs")
        }
        assert {
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            "idempotency_key",
            "reservation_id",
            "estimated_credit_units",
            "provider_reported_cost",
            "result_count",
        }.issubset(listing_discovery_cols)
        reputation_review_cols = {
            col["name"] for col in inspector.get_columns("reputation_reviews")
        }
        assert {
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            "source_type",
            "external_review_id",
            "response_status",
            "response_text",
            "provider_updated_at",
            "last_seen_at",
        }.issubset(reputation_review_cols)
        reputation_response_draft_cols = {
            col["name"] for col in inspector.get_columns("reputation_response_drafts")
        }
        assert {
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            "review_id",
            "policy_id",
            "governed_ai_run_id",
            "idempotency_key",
            "status",
            "risk_class",
            "sensitive_topics",
            "policy_snapshot",
            "review_snapshot",
            "evidence_refs",
            "draft_text",
            "approved_text",
            "reviewed_by_user_id",
        }.issubset(reputation_response_draft_cols)
        reputation_capability_cols = {
            col["name"]
            for col in inspector.get_columns("reputation_provider_capabilities")
        }
        assert {
            "tenant_id",
            "organization_id",
            "connection_id",
            "provider_method",
            "status",
            "proof_reference",
            "verified_at",
            "last_failure_code",
        }.issubset(reputation_capability_cols)
        reputation_execution_cols = {
            col["name"] for col in inspector.get_columns("reputation_response_executions")
        }
        assert {
            "tenant_id",
            "organization_id",
            "campaign_id",
            "review_id",
            "draft_id",
            "connection_id",
            "capability_id",
            "platform_job_id",
            "status",
            "approved_text_hash",
            "confirmation_hash",
            "provider_receipt",
            "attempt_count",
            "posted_at",
        }.issubset(reputation_execution_cols)
        assert "sub_account_id" in campaign_cols
        assert "business_location_id" in campaign_cols
        assert "sub_account_id" in business_location_cols
        assert {
            "city",
            "region",
            "country_code",
            "address_line1",
            "postal_code",
            "latitude",
            "longitude",
            "coordinate_precision",
            "coordinate_source",
            "provider_location_code",
            "provider_location_name",
            "provider_location_type",
            "provider_location_resolved_at",
        }.issubset(business_location_cols)
        assert "ix_campaigns_business_location_id" in campaign_indexes
        assert "ix_business_locations_sub_account_id" in business_location_indexes
        assert "sub_account_id" in report_schedule_cols
        assert "sub_account_id" in metric_cols
        assert "campaign_id" in metric_cols
        assert {
            "tenant_id",
            "idempotency_key",
            "max_retries",
            "available_at",
            "locked_at",
            "lease_expires_at",
            "locked_by",
        }.issubset(platform_job_cols)
        assert "ix_platform_jobs_claimable" in platform_job_indexes
        assert "uq_platform_jobs_idempotency_key" in platform_job_indexes
        assert "ix_provider_execution_metrics_tenant_campaign_created_at" in metric_indexes
        assert "organization_id" in campaign_daily_metric_cols
        assert "metric_date" in campaign_daily_metric_cols
        assert "deterministic_hash" in campaign_daily_metric_cols
        assert "ix_campaign_daily_metrics_campaign_date" in campaign_daily_metric_indexes
        assert (
            "ix_search_console_daily_metrics_campaign_date" in search_console_daily_metric_indexes
        )
        assert {
            "ctr",
            "property_uri",
            "search_type",
            "dimensions",
            "filters",
            "metric_contract_versions",
            "scope_key",
            "captured_at",
        }.issubset(search_console_daily_metric_cols)
        assert "ix_analytics_daily_metrics_campaign_date" in analytics_daily_metric_indexes
        assert "ix_keyword_daily_economics_keyword_date" in keyword_daily_economics_indexes
        assert "ix_keyword_market_snapshots_geo_device_date" in keyword_market_snapshot_indexes

        tenant_cols = {col["name"] for col in inspector.get_columns("tenants")}
        assert "status" in tenant_cols
        assert "setup_state" in campaign_cols
        assert "manual_automation_lock" in campaign_cols
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
        if engine is not None:
            engine.dispose()
        shutil.rmtree(tmp, ignore_errors=True)
