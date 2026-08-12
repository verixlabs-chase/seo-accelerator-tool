from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SupportCategory = Literal[
    "setup",
    "connection",
    "data_not_updating",
    "results_question",
    "recommended_action",
    "report",
    "billing",
    "other",
]
SupportPage = Literal[
    "/dashboard",
    "/settings",
    "/rankings",
    "/local-visibility",
    "/site-health",
    "/opportunities",
    "/reports",
    "/reviews",
    "/keyword-research",
    "/locations",
    "/help",
    "/other",
]


class SupportRequestCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: SupportCategory
    page_path: SupportPage
    customer_summary: str = Field(min_length=10, max_length=800)
    campaign_id: str | None = Field(default=None, min_length=36, max_length=36)
    diagnostic_consent: bool = False
    operator_access_consent: bool = False


class SupportRequestEscalateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Literal["setup_blocked", "data_missing", "deadline_passed", "business_impact"]


class SupportRequestStatusPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["received", "investigating", "waiting_for_customer", "resolved", "escalated"]
    note_code: Literal[
        "triage_started",
        "more_information_needed",
        "fix_in_progress",
        "customer_confirmed",
        "resolved_by_support",
        "priority_review",
    ]
