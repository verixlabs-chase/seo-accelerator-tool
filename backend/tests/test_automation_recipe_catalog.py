from __future__ import annotations

import pytest

from app.automation import (
    AUTOMATION_RECIPE_CATALOG_VERSION,
    automation_starter_recipe_catalog,
)


LIVE_EVENTS = frozenset(
    {"report.ready", "recommendation.ready", "action.completed", "action.failed"}
)


def test_starter_recipes_are_versioned_live_and_outbound_only() -> None:
    items = automation_starter_recipe_catalog(live_event_types=LIVE_EVENTS)

    assert {item["code"] for item in items} == {
        "owner_report_ready",
        "review_new_work",
        "track_action_results",
    }
    for item in items:
        assert item["version"] == AUTOMATION_RECIPE_CATALOG_VERSION
        assert set(item["event_types"]).issubset(LIVE_EVENTS)
        assert item["outbound_only"] is True
        assert item["human_approval_preserved"] is True
        assert item["automatic_actions_enabled"] is False


def test_starter_recipe_catalog_fails_closed_when_an_event_is_not_live() -> None:
    with pytest.raises(RuntimeError, match="non-live event"):
        automation_starter_recipe_catalog(live_event_types=frozenset({"report.ready"}))
