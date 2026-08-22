from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NotificationItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    schema_version: Literal["alt1-notification-v1"]
    organization_id: str
    organization_name: str
    location_id: str | None
    location_name: str | None
    event_type: Literal["report.ready", "action.failed"]
    severity: Literal["information", "needs_attention"]
    source_event_id: str
    source_event_type: str
    source_label: str
    resource_type: Literal["report", "action"]
    resource_id: str
    title: str
    meaning: str
    action_label: str
    action_url: str
    freshness_at: datetime
    observed_at: datetime
    created_at: datetime
    is_read: bool
    read_at: datetime | None
    is_dismissed: bool
    dismissed_at: datetime | None


class NotificationListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NotificationItemOut]
    unread_count: int = Field(ge=0)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class NotificationUnreadCountOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unread_count: int = Field(ge=0)
    count: int = Field(ge=0)


class NotificationMutationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification: NotificationItemOut
    unread_count: int = Field(ge=0)
