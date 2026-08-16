from pathlib import Path


def test_content_draft_migration_is_scoped_and_never_auto_publishes() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260815_0159_content_working_drafts.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260815_0159"' in migration
    assert 'down_revision = "20260815_0158"' in migration
    assert "fk_content_drafts_brief_scope" in migration
    assert "automatic_publishing_allowed = false" in migration
    assert "content_drafts_scope" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "REVOKE DELETE" in migration
    upgrade_body = migration.split("def upgrade", 1)[1].split("def downgrade", 1)[0]
    assert "DROP TABLE" not in upgrade_body.upper()
