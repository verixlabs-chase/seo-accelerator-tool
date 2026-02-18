import os
import shutil
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_migration_upgrade_and_downgrade():
    tmp_root = Path(".tmp_test_migrations")
    tmp_root.mkdir(exist_ok=True)
    tmp = tmp_root / str(uuid.uuid4())
    tmp.mkdir(exist_ok=True)
    try:
        db_path = os.path.join(str(tmp.resolve()), "mig.db")
        dsn = f"sqlite:///{db_path}"
        os.environ["POSTGRES_DSN"] = dsn

        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", dsn)

        command.upgrade(cfg, "head")
        engine = create_engine(dsn)
        inspector = inspect(engine)
        assert "campaigns" in inspector.get_table_names()
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
        tenant_cols = {col["name"] for col in inspector.get_columns("tenants")}
        campaign_cols = {col["name"] for col in inspector.get_columns("campaigns")}
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
        shutil.rmtree(tmp, ignore_errors=True)
