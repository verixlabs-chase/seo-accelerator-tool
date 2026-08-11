from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


NonBlankGroupName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
SafeTargetingKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    ),
]


class LocationGroupCreateIn(BaseModel):
    name: NonBlankGroupName
    description: str | None = Field(default=None, max_length=1000)
    location_ids: list[str] = Field(min_length=1, max_length=500)


class LocationGroupUpdateIn(BaseModel):
    expected_version: int = Field(ge=1)
    name: NonBlankGroupName
    description: str | None = Field(default=None, max_length=1000)
    status: Literal["active", "archived"] = "active"
    location_ids: list[str] = Field(min_length=1, max_length=500)


class TargetSnapshotCreateIn(BaseModel):
    action_key: SafeTargetingKey = Field(max_length=80)
    request_key: SafeTargetingKey
    location_group_id: str | None = Field(default=None, max_length=36)
    select_all_active: bool = False
    regions: list[str] = Field(default_factory=list, max_length=50)
    included_location_ids: list[str] = Field(default_factory=list, max_length=500)
    excluded_location_ids: list[str] = Field(default_factory=list, max_length=500)
