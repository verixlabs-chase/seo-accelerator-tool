from __future__ import annotations

from dataclasses import dataclass


AUTOMATION_RECIPE_CATALOG_VERSION = "insightos.automation.recipes.v1"


@dataclass(frozen=True)
class AutomationStarterRecipe:
    code: str
    label: str
    summary: str
    external_result: str
    event_types: tuple[str, ...]


_STARTER_RECIPES: tuple[AutomationStarterRecipe, ...] = (
    AutomationStarterRecipe(
        code="owner_report_ready",
        label="Share new reports",
        summary=(
            "Notify your existing workflow when an owner-ready InsightOS report "
            "has been saved."
        ),
        external_result="Create a task, message, or client follow-up outside InsightOS.",
        event_types=("report.ready",),
    ),
    AutomationStarterRecipe(
        code="review_new_work",
        label="Review work that needs attention",
        summary=(
            "Send new evidence-backed recommendations and stopped actions to a "
            "human review queue."
        ),
        external_result="Create a review task without approving or running the work.",
        event_types=("recommendation.ready", "action.failed"),
    ),
    AutomationStarterRecipe(
        code="track_action_results",
        label="Track action results",
        summary=(
            "Record when an approved InsightOS action completes or needs recovery."
        ),
        external_result="Update an operations log or notify the responsible teammate.",
        event_types=("action.completed", "action.failed"),
    ),
)


def automation_starter_recipe_catalog(
    *, live_event_types: frozenset[str]
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for recipe in _STARTER_RECIPES:
        if not set(recipe.event_types).issubset(live_event_types):
            raise RuntimeError(
                f"Automation starter recipe {recipe.code!r} references a non-live event."
            )
        items.append(
            {
                "code": recipe.code,
                "version": AUTOMATION_RECIPE_CATALOG_VERSION,
                "label": recipe.label,
                "summary": recipe.summary,
                "external_result": recipe.external_result,
                "event_types": list(recipe.event_types),
                "outbound_only": True,
                "human_approval_preserved": True,
                "automatic_actions_enabled": False,
            }
        )
    return items
