from pathlib import Path


def test_enterprise_report_logo_migration_is_bounded_and_preserves_customer_assets() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260820_0201_enterprise_report_logo.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260820_0201"' in migration
    assert 'down_revision = "20260820_0200"' in migration
    assert 'sa.Column("logo_content", sa.LargeBinary(), nullable=True)' in migration
    assert "ck_org_report_brands_logo_complete" in migration
    assert "length(logo_content) >= 1" in migration
    assert "length(logo_content) <= 65536" in migration
    assert "ck_org_report_brands_logo_dimensions" in migration
    assert "Cannot downgrade while an Enterprise report logo exists" in migration
