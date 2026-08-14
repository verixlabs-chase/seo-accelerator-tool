from pathlib import Path


def test_governed_experiment_plan_migration_is_tenant_and_org_scoped() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260814_0150_governed_experiment_plans.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "20260814_0149"' in migration
    assert '"governed_experiment_plans"' in migration
    assert "uq_governed_experiment_plans_tenant_idempotency" in migration
    assert "created_by_user_id" in migration
    assert "reviewed_by_user_id" in migration
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FOR ALL TO lsos_app" in migration
    assert "app.current_tenant_id" in migration
    assert "app.current_organization_id" in migration
