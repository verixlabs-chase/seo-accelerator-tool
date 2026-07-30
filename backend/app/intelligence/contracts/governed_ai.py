from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class GovernedIntelligenceBrief(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(min_length=1, max_length=800)
    why_now: str = Field(min_length=1, max_length=800)
    selected_action_id: str | None = Field(default=None, max_length=160)
    evidence_used: list[str] = Field(min_length=1, max_length=12)
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

    def validate_against_context(
        self,
        *,
        evidence_ids: set[str],
        deterministic_action_id: str | None,
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
