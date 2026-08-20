from pathlib import Path


def test_enterprise_report_branding_migration_is_scoped_and_preserves_data_on_downgrade() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260819_0199_enterprise_report_branding.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260819_0199"' in migration
    assert 'down_revision = "20260819_0198"' in migration
    assert "tenant_id = organization_id" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "current_organization_id" in migration
    assert "REVOKE DELETE" in migration
    assert "Cannot downgrade while Enterprise report branding exists" in migration
