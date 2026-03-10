from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PatternPayload(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    pattern_key: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Any] = Field(default_factory=list)


class PatternBundle(BaseModel):
    model_config = ConfigDict(extra='forbid')

    patterns: list[PatternPayload]
