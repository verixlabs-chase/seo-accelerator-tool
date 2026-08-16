from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ContentAssetCreateIn(BaseModel):
    campaign_id: str
    cluster_name: str
    title: str
    planned_month: int = 1


class ContentAssetUpdateIn(BaseModel):
    status: str | None = None
    title: str | None = None
    target_url: str | None = None


class ContentBriefReviewIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)
    decision: Literal["accept", "decline"]
    note: str | None = Field(default=None, max_length=500)


class ContentDraftCreateIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)


class ContentDraftAISuggestionIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)


class ContentDraftSectionIn(BaseModel):
    order: int = Field(ge=1, le=20)
    heading: str = Field(min_length=1, max_length=160)
    body: str = Field(default="", max_length=3000)


class ContentDraftUpdateIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=320)
    sections: list[ContentDraftSectionIn] = Field(min_length=1, max_length=12)


class ContentPublishingHandoffIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)


class ContentPublishingApprovalIn(ContentPublishingHandoffIn):
    preview_hash: str = Field(min_length=64, max_length=64)
    reviewed_exact_preview: Literal[True]
    understands_wordpress_draft: Literal[True]
    understands_not_public: Literal[True]


class ContentPublishingDeliveryIn(ContentPublishingHandoffIn):
    preview_hash: str = Field(min_length=64, max_length=64)
    create_non_public_draft: Literal[True]


class ContentAssetOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    cluster_name: str
    title: str
    status: str
    target_url: str | None
    planned_month: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
