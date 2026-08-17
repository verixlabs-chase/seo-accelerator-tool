from pathlib import Path


def test_onboarding_baseline_migration_is_scoped_and_immutable() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260815_0157_onboarding_baseline.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260815_0157"' in migration
    assert 'down_revision = "20260815_0156"' in migration
    assert "fk_onboarding_baselines_campaign_scope" in migration
    assert "onboarding_baselines_scope" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "prevent_onboarding_baseline_mutation" in migration
    assert "REVOKE UPDATE, DELETE" in migration
    assert "evidence_window_days = 28" in migration
    upgrade_body = migration.split("def upgrade", 1)[1].split("def downgrade", 1)[0]
    assert "DROP TABLE" not in upgrade_body.upper()
