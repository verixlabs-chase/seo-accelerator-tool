from pathlib import Path


def test_enterprise_report_accent_migration_is_additive_and_preserves_custom_values() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260820_0200_enterprise_report_accent.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260820_0200"' in migration
    assert 'down_revision = "20260819_0199"' in migration
    assert 'server_default=DEFAULT_ACCENT' in migration
    assert "ck_org_report_brands_accent" in migration
    assert "Cannot downgrade while a custom Enterprise report accent exists" in migration
