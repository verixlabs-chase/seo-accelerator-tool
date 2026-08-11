from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


SafeIdempotencyKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    ),
]
SafeSubjectId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    ),
]


class ProductEventCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_name: str = Field(min_length=1, max_length=100)
    campaign_id: str | None = Field(default=None, min_length=36, max_length=36)
    properties: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None
    idempotency_key: SafeIdempotencyKey | None = None


class ProductFeedbackCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: Literal[
        "recommendation_usefulness",
        "explanation_clarity",
        "forecast_trust",
        "automation_confidence",
        "report_quality",
    ]
    subject_type: Literal["recommendation", "explanation", "forecast", "automation", "report"]
    subject_id: SafeSubjectId | None = None
    campaign_id: str | None = Field(default=None, min_length=36, max_length=36)
    rating: int = Field(ge=1, le=5)
    reason_code: Literal[
        "useful",
        "clear",
        "believable",
        "not_useful_yet",
        "unclear",
        "missing_context",
        "too_technical",
        "not_believable",
    ]
