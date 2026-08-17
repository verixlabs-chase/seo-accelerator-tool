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


class GovernedContentDraftSectionSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    order: int = Field(ge=1, le=20)
    heading: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=1500)


class GovernedContentDraftSuggestion(BaseModel):
    """Optional wording that remains separate from an owner-controlled draft."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    draft_id: str = Field(min_length=1, max_length=36)
    suggestion_state: Literal["ready", "not_enough_information"]
    suggested_title: str = Field(min_length=1, max_length=320)
    sections: list[GovernedContentDraftSectionSuggestion] = Field(
        default_factory=list,
        max_length=12,
    )
    evidence_used: list[str] = Field(default_factory=list, max_length=12)
    uncertainties: list[str] = Field(default_factory=list, max_length=8)
    approval_required: bool
    can_publish: Literal[False]

    @model_validator(mode="after")
    def suggestion_copy_is_safe(self) -> "GovernedContentDraftSuggestion":
        if not self.approval_required:
            raise ValueError("Every AI wording suggestion must require owner review.")
        if self.suggestion_state == "ready":
            if not self.evidence_used:
                raise ValueError("Ready wording must cite supplied evidence.")
            if not self.sections:
                raise ValueError("Ready wording must include the requested sections.")
            combined = " ".join(
                [self.suggested_title]
                + [f"{item.heading} {item.body}" for item in self.sections]
            )
            disallowed = find_disallowed_customer_terms(combined)
            if disallowed:
                raise ValueError(f"AI wording used technical language: {disallowed[0]}")
            if re.search(r"\d", combined):
                raise ValueError("AI wording cannot introduce numeric business claims.")
            lowered = combined.lower()
            unsupported = [
                phrase
                for phrase in UNSUPPORTED_DRAFT_CLAIM_PHRASES
                if phrase in lowered
            ]
            if unsupported:
                raise ValueError(
                    f"AI wording contained an unsupported business claim: {unsupported[0]}"
                )
            for safe_phrase in SAFE_NEGATIONS:
                lowered = lowered.replace(safe_phrase, "")
            unsupported_outcomes = [
                phrase for phrase in UNSUPPORTED_CLAIM_PHRASES if phrase in lowered
            ]
            if unsupported_outcomes:
                raise ValueError(
                    "AI wording contained an unsupported outcome claim: "
                    f"{unsupported_outcomes[0]}"
                )
        return self

    def validate_against_context(
        self,
        *,
        draft_id: str,
        section_orders: list[int],
        evidence_ids: set[str],
    ) -> None:
        if self.draft_id != draft_id:
            raise ValueError("AI output changed the working draft identifier.")
        if self.suggestion_state == "ready":
            returned_orders = [item.order for item in self.sections]
            if returned_orders != section_orders:
                raise ValueError("AI output changed the requested section order.")
        unknown_evidence = sorted(set(self.evidence_used) - evidence_ids)
        if unknown_evidence:
            raise ValueError(
                f"AI output cited evidence outside the supplied context: {unknown_evidence}"
            )


class GovernedKeywordRelevanceDecision(BaseModel):
    """One bounded classification of a server-selected uncertain search phrase."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    suggestion_id: str = Field(min_length=1, max_length=36)
    classification: Literal["relevant", "unrelated", "still_unclear"]
    confidence: float = Field(ge=0, le=1)
    matched_service_id: str | None = Field(default=None, max_length=36)
    matched_service_area_id: str | None = Field(default=None, max_length=36)
    area_basis: Literal[
        "included_area",
        "confirmed_market",
        "excluded_area",
        "unclear",
    ]
    reason: str = Field(min_length=1, max_length=320)
    evidence_used: list[str] = Field(min_length=1, max_length=8)

    @field_validator("reason")
    @classmethod
    def reason_must_be_plain_language(cls, value: str) -> str:
        return _validate_plain_language(
            value,
            field_name="reason",
            max_words=40,
            max_sentences=2,
            require_action_start=False,
        )

    @field_validator("evidence_used")
    @classmethod
    def evidence_must_be_unique(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            stripped = item.strip()
            if not stripped:
                raise ValueError("Evidence identifiers must not be empty.")
            if stripped not in normalized:
                normalized.append(stripped)
        return normalized

    @model_validator(mode="after")
    def relevant_decisions_require_business_facts(self) -> "GovernedKeywordRelevanceDecision":
        if self.classification == "relevant":
            if self.matched_service_id is None:
                raise ValueError("A relevant search must match a confirmed service.")
            if self.area_basis not in {"included_area", "confirmed_market"}:
                raise ValueError("A relevant search must use a confirmed service market.")
        if self.area_basis == "included_area" and self.matched_service_area_id is None:
            raise ValueError("An included-area decision must identify that service area.")
        if self.area_basis == "excluded_area" and self.matched_service_area_id is None:
            raise ValueError("An excluded-area decision must identify that service area.")
        return self


class GovernedKeywordRelevanceReview(BaseModel):
    """Strict batch output for uncertain keyword review; never an open-ended chat response."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decisions: list[GovernedKeywordRelevanceDecision] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def suggestion_ids_must_be_unique(self) -> "GovernedKeywordRelevanceReview":
        ids = [item.suggestion_id for item in self.decisions]
        if len(ids) != len(set(ids)):
            raise ValueError("Each search suggestion may appear only once.")
        return self

    def validate_against_context(
        self,
        *,
        suggestion_ids: set[str],
        service_ids: set[str],
        included_area_ids: set[str],
        excluded_area_ids: set[str],
        evidence_ids: set[str],
    ) -> None:
        returned_ids = {item.suggestion_id for item in self.decisions}
        if returned_ids != suggestion_ids:
            raise ValueError("AI output must classify every supplied search exactly once.")
        for item in self.decisions:
            if item.matched_service_id and item.matched_service_id not in service_ids:
                raise ValueError("AI output referenced a service outside the confirmed profile.")
            if item.matched_service_area_id:
                allowed_area_ids = included_area_ids | excluded_area_ids
                if item.matched_service_area_id not in allowed_area_ids:
                    raise ValueError("AI output referenced an unknown service area.")
            if (
                item.area_basis == "included_area"
                and item.matched_service_area_id not in included_area_ids
            ):
                raise ValueError("AI output treated an unconfirmed area as included.")
            if (
                item.area_basis == "excluded_area"
                and item.matched_service_area_id not in excluded_area_ids
            ):
                raise ValueError("AI output treated an included area as excluded.")
            if item.area_basis == "confirmed_market" and not included_area_ids:
                raise ValueError("AI output used a confirmed market when none exists.")
            unknown_evidence = sorted(set(item.evidence_used) - evidence_ids)
            if unknown_evidence:
                raise ValueError(
                    f"AI output cited evidence outside the supplied context: {unknown_evidence}"
                )


class GovernedBaselineTheme(BaseModel):
    """One plain-language theme grounded in frozen onboarding evidence."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=100)
    explanation: str = Field(min_length=1, max_length=700)
    evidence_used: list[str] = Field(min_length=1, max_length=8)

    @field_validator("title")
    @classmethod
    def title_must_be_plain_language(cls, value: str) -> str:
        return _validate_plain_language(
            value,
            field_name="baseline theme title",
            max_words=12,
            max_sentences=1,
            require_action_start=False,
        )

    @field_validator("explanation")
    @classmethod
    def explanation_must_be_plain_language(cls, value: str) -> str:
        return _validate_plain_language(
            value,
            field_name="baseline theme explanation",
            max_words=70,
            max_sentences=3,
            require_action_start=False,
        )

    @field_validator("evidence_used")
    @classmethod
    def evidence_must_be_unique(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            stripped = item.strip()
            if not stripped:
                raise ValueError("Evidence identifiers must not be empty.")
            if stripped not in normalized:
                normalized.append(stripped)
        return normalized


class GovernedBaselineNarrative(BaseModel):
    """Bounded AI wording for an immutable deterministic onboarding baseline."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    headline: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=1400)
    themes: list[GovernedBaselineTheme] = Field(default_factory=list, max_length=4)
    priority_order: list[str] = Field(default_factory=list, max_length=10)
    evidence_used: list[str] = Field(min_length=1, max_length=20)
    uncertainties: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("headline")
    @classmethod
    def headline_must_be_plain_language(cls, value: str) -> str:
        return _validate_plain_language(
            value,
            field_name="baseline headline",
            max_words=16,
            max_sentences=1,
            require_action_start=False,
        )

    @field_validator("summary")
    @classmethod
    def summary_must_be_plain_language(cls, value: str) -> str:
        return _validate_plain_language(
            value,
            field_name="baseline narrative",
            max_words=130,
            max_sentences=6,
            require_action_start=False,
        )

    @field_validator("priority_order", "evidence_used", "uncertainties")
    @classmethod
    def list_items_must_be_unique(cls, value: list[str]) -> list[str]:
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
        deterministic_fix_ids: list[str],
    ) -> None:
        cited_evidence = set(self.evidence_used)
        for theme in self.themes:
            cited_evidence.update(theme.evidence_used)
        unknown_evidence = sorted(cited_evidence - evidence_ids)
        if unknown_evidence:
            raise ValueError(
                f"AI output cited evidence outside the frozen baseline: {unknown_evidence}"
            )
        if self.priority_order != deterministic_fix_ids:
            raise ValueError(
                "AI output changed, removed, added, or reordered the deterministic fix plan."
            )
        combined_text = " ".join(
            [
                self.headline,
                self.summary,
                *(theme.title for theme in self.themes),
                *(theme.explanation for theme in self.themes),
                *self.uncertainties,
            ]
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
