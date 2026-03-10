from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SignalPayload(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    signal_name: str = Field(min_length=1)
    source: str = Field(min_length=1)
    value: Any
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class SignalBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')

    signals: list[SignalPayload]
