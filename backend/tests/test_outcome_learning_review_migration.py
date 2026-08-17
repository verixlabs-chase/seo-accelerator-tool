from pathlib import Path


def test_outcome_learning_review_migration_is_tenant_and_org_scoped() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260814_0149_outcome_learning_reviews.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "20260813_0148"' in migration
    assert '"outcome_learning_reviews"' in migration
    assert "uq_outcome_learning_reviews_measurement_id" in migration
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FOR ALL TO lsos_app" in migration
    assert "app.current_tenant_id" in migration
    assert "app.current_organization_id" in migration
