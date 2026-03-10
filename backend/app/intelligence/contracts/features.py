from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FeaturePayload(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    feature_name: str = Field(min_length=1)
    value: float
    source_signals: list[str] = Field(default_factory=list)


class FeatureBundle(BaseModel):
    model_config = ConfigDict(extra='forbid')

    features: list[FeaturePayload]
