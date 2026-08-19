from __future__ import annotations

from dataclasses import asdict, dataclass


CAPABILITY_CATALOG_VERSION = "private-ai-capabilities-v1"


@dataclass(frozen=True)
class PrivateAICapabilityDefinition:
    code: str
    label: str
    summary: str
    output_boundary: str
    fixed_canary_percentage: int = 5
    shared_workspace_prompt_limit_per_day: int = 1
    separate_qualification_required: bool = True
    owner_approval_required: bool = True
    managed_fallback_required: bool = True
    automatic_rollback: bool = True
    automatic_changes_allowed: bool = False
    publishing_allowed: bool = False


CAPABILITY_CATALOG = (
    PrivateAICapabilityDefinition(
        code="intelligence_brief",
        label="Daily explanations",
        summary="Explains saved InsightOS evidence in the daily brief.",
        output_boundary="Explanation only",
    ),
    PrivateAICapabilityDefinition(
        code="intelligence_question",
        label="Saved-evidence questions",
        summary="Answers an owner's question using saved evidence.",
        output_boundary="Answer only",
    ),
    PrivateAICapabilityDefinition(
        code="intelligence_draft",
        label="Saved-action draft wording",
        summary="Suggests wording for an existing saved action draft.",
        output_boundary="Draft suggestion only",
    ),
    PrivateAICapabilityDefinition(
        code="keyword_relevance_review",
        label="Unclear-search review",
        summary="Classifies only unclear saved searches for owner review.",
        output_boundary="Saved-search classification only",
    ),
    PrivateAICapabilityDefinition(
        code="content_draft_suggestion",
        label="Optional website draft wording",
        summary="Suggests alternative wording for an existing website draft.",
        output_boundary="Draft suggestion only",
    ),
    PrivateAICapabilityDefinition(
        code="onboarding_baseline_narrative",
        label="Optional baseline explanation",
        summary=(
            "Explains the saved onboarding baseline without changing its score or fixes."
        ),
        output_boundary="Explanation only",
    ),
    PrivateAICapabilityDefinition(
        code="review_response_draft",
        label="Optional review reply wording",
        summary=(
            "Suggests reply wording for an eligible saved review; it cannot post."
        ),
        output_boundary="Draft suggestion only",
    ),
)

CAPABILITY_CODES = tuple(item.code for item in CAPABILITY_CATALOG)


def serialize_capability_catalog() -> list[dict[str, object]]:
    return [asdict(item) for item in CAPABILITY_CATALOG]
