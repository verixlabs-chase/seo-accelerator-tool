from pathlib import Path


def test_execution_queue_migration_grants_campaign_scoped_access() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260813_0135_execution_queue_rls.py"
    ).read_text(encoding="utf-8")

    for table in ("recommendation_executions", "execution_mutations"):
        assert table in migration

    assert "GRANT SELECT, INSERT, UPDATE, DELETE" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FOR ALL TO lsos_app" in migration
    assert "public.campaigns AS scoped_campaign" in migration
    assert "app.current_tenant_id" in migration
    assert "app.current_organization_id" in migration
