from pathlib import Path

import pytest

from app.providers import authority, competitor, local, rank


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "rel_path",
    [
        "app/providers/rank.py",
        "app/providers/local.py",
        "app/providers/authority.py",
        "app/providers/retry.py",
        "app/services/competitor_service.py",
        "app/services/reporting_service.py",
        "app/tasks/tasks.py",
    ],
)
def test_execution_paths_do_not_use_random_module(rel_path: str) -> None:
    text = _read(rel_path)
    assert "import random" not in text
    assert "from random import" not in text


@pytest.mark.parametrize(
    "rel_path",
    [
        "app/tasks/tasks.py",
        "app/services/reporting_service.py",
        "app/services/competitor_service.py",
        "app/services/strategy_engine/thresholds.py",
        "app/services/strategy_engine/scenario_registry.py",
    ],
)
def test_execution_paths_do_not_contain_placeholders(rel_path: str) -> None:
    text = _read(rel_path).lower()
    assert "placeholder" not in text
    assert "example.com/citations" not in text


def test_rank_provider_requires_explicit_non_fixture_backend(monkeypatch) -> None:
    rank.get_rank_provider.cache_clear()
    monkeypatch.setattr(
        rank,
        "get_settings",
        lambda: type("S", (), {"rank_provider_backend": "synthetic", "app_env": "production"})(),
    )
    with pytest.raises(ValueError, match="fixture-only"):
        rank.get_rank_provider()
    rank.get_rank_provider.cache_clear()


def test_local_provider_requires_explicit_non_fixture_backend(monkeypatch) -> None:
    local.get_local_provider.cache_clear()
    monkeypatch.setattr(
        local,
        "get_settings",
        lambda: type("S", (), {"local_provider_backend": "synthetic", "app_env": "production"})(),
    )
    with pytest.raises(ValueError, match="test fixture mode"):
        local.get_local_provider()
    local.get_local_provider.cache_clear()


def test_authority_provider_requires_explicit_non_fixture_backend(monkeypatch) -> None:
    authority.get_authority_provider.cache_clear()
    monkeypatch.setattr(
        authority,
        "get_settings",
        lambda: type("S", (), {"authority_provider_backend": "synthetic", "app_env": "production"})(),
    )
    with pytest.raises(ValueError, match="test fixture mode"):
        authority.get_authority_provider()
    authority.get_authority_provider.cache_clear()


def test_competitor_provider_fixture_is_test_only(monkeypatch) -> None:
    monkeypatch.setattr(
        competitor,
        "get_settings",
        lambda: type("S", (), {"competitor_provider_backend": "fixture", "app_env": "production"})(),
    )
    with pytest.raises(ValueError, match="test mode"):
        competitor.get_competitor_provider_for_organization(db=None, organization_id="org-1")
