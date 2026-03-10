from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MutationPayload(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    mutation_type: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    rollback_plan: dict[str, Any] = Field(default_factory=dict)


class MutationBundle(BaseModel):
    model_config = ConfigDict(extra='forbid')

    mutations: list[MutationPayload]
