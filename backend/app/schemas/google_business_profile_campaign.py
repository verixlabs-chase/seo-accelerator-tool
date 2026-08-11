from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints


SafeRequestKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    ),
]


class ProfileCampaignCreateIn(BaseModel):
    target_snapshot_id: str = Field(min_length=36, max_length=36)
    request_key: SafeRequestKey
    name: str = Field(min_length=1, max_length=160)
    action_type: Literal["local_post", "photo_upload"]
    payload_template: dict[str, Any]
    scheduled_for: datetime | None = None


class ProfileCampaignDecisionIn(BaseModel):
    expected_version: int = Field(ge=1)
