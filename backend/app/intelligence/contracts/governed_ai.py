from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.intelligence.lexicon.plain_language import (
    SUMMARY_MAX_WORDS,
    WHY_NOW_MAX_WORDS,
    find_disallowed_customer_terms,
    sentence_count,
    starts_with_action,
    word_count,
)


UNSUPPORTED_CLAIM_PHRASES = (
    "guarantee",
    "guaranteed",
    "will rank",
    "will increase revenue",
    "will increase leads",
    "proves that",
    "definitely caused",
)
SAFE_NEGATIONS = (
    "not guaranteed",
    "no guarantee",
    "cannot guarantee",
    "can't guarantee",
    "does not guarantee",
    "doesn't guarantee",
)
ANSWER_MAX_WORDS = 90
DRAFT_TYPES = Literal[
    "search_result",
    "review_request",
    "review_response",
    "page_outline",
]
DRAFT_LIMITS = {
    "search_result": {"title": 70, "body": 180},
    "review_request": {"title": 120, "body": 500},
    "review_response": {"title": 120, "body": 600},
    "page_outline": {"title": 100, "body": 1800},
}
UNSUPPORTED_DRAFT_CLAIM_PHRASES = (
    "award-winning",
    "best in",
    "cheapest",
    "family-owned",
    "free estimate",
    "guaranteed",
    "licensed and insured",
    "licensed & insured",
    "same-day",
    "top-rated",
    "years of experience",
)


class GovernedIntelligenceBrief(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(min_length=1, max_length=800)
    why_now: str = Field(min_length=1, max_length=800)
    selected_action_id: str | None = Field(default=None, max_length=160)
    daily_action_ids: list[str] = Field(default_factory=list, max_length=3)
    evidence_used: list[str] = Field(min_length=1, max_length=12)
    uncertainties: list[str] = Field(default_factory=list, max_length=8)
    approval_required: bool

    @field_validator("summary")
    @classmethod
    def summary_must_be_plain_language(cls, value: str) -> str:
        return _validate_plain_language(
            value,
            field_name="summary",
            max_words=SUMMARY_MAX_WORDS,
            max_sentences=2,
        )

    @field_validator("why_now")
    @classmethod
    def why_now_must_be_plain_language(cls, value: str) -> str:
        return _validate_plain_language(
            value,
            field_name="why_now",
            max_words=WHY_NOW_MAX_WORDS,
            max_sentences=1,
        )

    @field_validator("daily_action_ids", "evidence_used", "uncertainties")
    @classmethod
    def unique_nonempty_items(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            stripped = item.strip()
            if not stripped:
                raise ValueError("List items must not be empty.")
            if stripped not in normalized:
                normalized.append(stripped)
        return normalized

    def validate_against_context(
        self,
        *,
        evidence_ids: set[str],
        deterministic_action_id: str | None,
        deterministic_daily_action_ids: list[str],
        action_requires_approval: bool,
    ) -> None:
        unknown_evidence = sorted(set(self.evidence_used) - evidence_ids)
        if unknown_evidence:
            raise ValueError(
                f"AI output cited evidence outside the supplied context: {unknown_evidence}"
            )
        if self.selected_action_id != deterministic_action_id:
            raise ValueError(
                "AI output changed the deterministic selected action."
            )
        if self.daily_action_ids != deterministic_daily_action_ids:
            raise ValueError(
                "AI output changed the deterministic daily action plan."
            )
        if self.selected_action_id is not None and (
            not self.daily_action_ids
            or self.daily_action_ids[0] != self.selected_action_id
        ):
            raise ValueError(
                "The selected action must remain first in the daily action plan."
            )
        if self.approval_required is not action_requires_approval:
            raise ValueError(
                "AI output changed the deterministic approval requirement."
            )
        combined_text = f"{self.summary} {self.why_now}".lower()
        for safe_phrase in SAFE_NEGATIONS:
            combined_text = combined_text.replace(safe_phrase, "")
        unsupported = [
            phrase for phrase in UNSUPPORTED_CLAIM_PHRASES if phrase in combined_text
        ]
        if unsupported:
            raise ValueError(
                f"AI output contained an unsupported claim: {unsupported[0]}"
            )


class GovernedEvidenceAnswer(BaseModel):
    """A bounded answer grounded only in the supplied location evidence."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=3, max_length=500)
    answer: str = Field(min_length=1, max_length=1800)
    answer_state: Literal[
        "answered",
        "not_enough_information",
        "temporarily_unavailable",
    ]
    evidence_used: list[str] = Field(default_factory=list, max_length=12)
    related_action_ids: list[str] = Field(default_factory=list, max_length=3)
    uncertainties: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("answer")
    @classmethod
    def answer_must_be_plain_language(cls, value: str) -> str:
        return _validate_plain_language(
            value,
            field_name="answer",
            max_words=ANSWER_MAX_WORDS,
            max_sentences=4,
            require_action_start=False,
        )

    @field_validator("evidence_used", "related_action_ids", "uncertainties")
    @classmethod
    def unique_nonempty_items(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            stripped = item.strip()
            if not stripped:
                raise ValueError("List items must not be empty.")
            if stripped not in normalized:
                normalized.append(stripped)
        return normalized

    @model_validator(mode="after")
    def answered_state_requires_evidence(self) -> "GovernedEvidenceAnswer":
        if self.answer_state == "answered" and not self.evidence_used:
            raise ValueError("A verified answer must cite supplied evidence.")
        if self.answer_state != "answered" and self.related_action_ids:
            raise ValueError(
                "An unavailable answer cannot recommend a related action."
            )
        return self

    def validate_against_context(
        self,
        *,
        original_question: str,
        evidence_ids: set[str],
        allowed_action_ids: set[str],
    ) -> None:
        if self.question != original_question:
            raise ValueError("AI output changed the customer's question.")
        unknown_evidence = sorted(set(self.evidence_used) - evidence_ids)
        if unknown_evidence:
            raise ValueError(
                f"AI output cited evidence outside the supplied context: {unknown_evidence}"
            )
        unknown_actions = sorted(set(self.related_action_ids) - allowed_action_ids)
        if unknown_actions:
            raise ValueError(
                f"AI output referenced actions outside the supplied context: {unknown_actions}"
            )
        combined_text = " ".join(
            [self.answer, *self.uncertainties]
        ).lower()
        for safe_phrase in SAFE_NEGATIONS:
            combined_text = combined_text.replace(safe_phrase, "")
        unsupported = [
            phrase for phrase in UNSUPPORTED_CLAIM_PHRASES if phrase in combined_text
        ]
        if unsupported:
            raise ValueError(
                f"AI output contained an unsupported claim: {unsupported[0]}"
            )


class GovernedActionDraft(BaseModel):
    """Customer-facing copy drafted for one deterministic saved action."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action_id: str = Field(min_length=1, max_length=160)
    draft_type: DRAFT_TYPES
    draft_state: Literal[
        "ready",
        "not_enough_information",
        "temporarily_unavailable",
    ]
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=1800)
    evidence_used: list[str] = Field(default_factory=list, max_length=12)
    uncertainties: list[str] = Field(default_factory=list, max_length=8)
    approval_required: bool

    @field_validator("evidence_used", "uncertainties")
    @classmethod
    def unique_nonempty_items(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            stripped = item.strip()
            if not stripped:
                raise ValueError("List items must not be empty.")
            if stripped not in normalized:
                normalized.append(stripped)
        return normalized

    @model_validator(mode="after")
    def draft_state_and_copy_are_safe(self) -> "GovernedActionDraft":
        if not self.approval_required:
            raise ValueError("Every generated draft must require customer review.")
        if self.draft_state == "ready" and not self.evidence_used:
            raise ValueError("A ready draft must cite supplied evidence.")
        limits = DRAFT_LIMITS[self.draft_type]
        if len(self.title) > limits["title"]:
            raise ValueError(
                f"{self.draft_type} title must be {limits['title']} characters or fewer."
            )
        if len(self.body) > limits["body"]:
            raise ValueError(
                f"{self.draft_type} body must be {limits['body']} characters or fewer."
            )
        if self.draft_state == "ready":
            combined = f"{self.title} {self.body}"
            disallowed = find_disallowed_customer_terms(combined)
            if disallowed:
                raise ValueError(
                    f"Draft used technical language: {disallowed[0]}"
                )
            if re.search(r"\d", combined):
                raise ValueError(
                    "Drafts cannot introduce numeric claims in this bounded workflow."
                )
            lowered = combined.lower()
            unsupported = [
                phrase
                for phrase in UNSUPPORTED_DRAFT_CLAIM_PHRASES
                if phrase in lowered
            ]
            if unsupported:
                raise ValueError(
                    f"Draft contained an unsupported business claim: {unsupported[0]}"
                )
            for safe_phrase in SAFE_NEGATIONS:
                lowered = lowered.replace(safe_phrase, "")
            unsupported_outcomes = [
                phrase for phrase in UNSUPPORTED_CLAIM_PHRASES if phrase in lowered
            ]
            if unsupported_outcomes:
                raise ValueError(
                    "Draft contained an unsupported outcome claim: "
                    f"{unsupported_outcomes[0]}"
                )
        return self

    def validate_against_context(
        self,
        *,
        requested_action_id: str,
        requested_draft_type: str,
        evidence_ids: set[str],
        allowed_action_ids: set[str],
        allowed_draft_types: set[str],
    ) -> None:
        if self.action_id != requested_action_id:
            raise ValueError("AI output changed the selected saved action.")
        if self.action_id not in allowed_action_ids:
            raise ValueError("AI output referenced an action outside the supplied context.")
        if self.draft_type != requested_draft_type:
            raise ValueError("AI output changed the requested draft type.")
        if self.draft_type not in allowed_draft_types:
            raise ValueError("The requested draft type is not allowed for this action.")
        unknown_evidence = sorted(set(self.evidence_used) - evidence_ids)
        if unknown_evidence:
            raise ValueError(
                f"AI output cited evidence outside the supplied context: {unknown_evidence}"
            )


def _validate_plain_language(
    value: str,
    *,
    field_name: str,
    max_words: int,
    max_sentences: int,
    require_action_start: bool = True,
) -> str:
    disallowed = find_disallowed_customer_terms(value)
    if disallowed:
        raise ValueError(
            f"{field_name} used technical language: {disallowed[0]}"
        )
    actual_words = word_count(value)
    if actual_words > max_words:
        raise ValueError(
            f"{field_name} must be {max_words} words or fewer; received {actual_words}"
        )
    actual_sentences = sentence_count(value)
    if actual_sentences > max_sentences:
        raise ValueError(
            f"{field_name} must be {max_sentences} sentence"
            f"{'s' if max_sentences != 1 else ''} or fewer"
        )
    if require_action_start and field_name == "summary" and not starts_with_action(value):
        raise ValueError("summary must start with a clear action verb")
    return value
