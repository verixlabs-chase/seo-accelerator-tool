from __future__ import annotations

import importlib.util
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260817_0164_tier_profile_catalog_read_policy.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("tier_profile_catalog_read_0164", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tier_profile_catalog_policy_migration_contract() -> None:
    migration = _load_migration()
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert migration.revision == "20260817_0164"
    assert migration.down_revision == "20260817_0163"
    assert "GRANT SELECT ON TABLE public.tier_profiles TO lsos_app" in source
    assert "CREATE POLICY tier_profiles_global_read" in source
    assert "FOR SELECT" in source
    assert "TO lsos_app" in source
    assert "USING (true)" in source
    assert "GRANT INSERT" not in source
    assert "GRANT UPDATE" not in source
    assert "GRANT DELETE" not in source
