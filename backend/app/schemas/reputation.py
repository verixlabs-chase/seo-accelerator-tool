from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field


class ReputationReviewOut(BaseModel):
    id: str
    campaign_id: str
    business_location_id: str
    source_key: str
    source_name: str
    source_type: str
    external_review_id: str
    review_url: str | None
    rating: float
    body: str | None
    author_name: str | None
    author_is_anonymous: bool
    response_status: str
    response_text: str | None
    response_updated_at: datetime | None
    reviewed_at: datetime
    provider_updated_at: datetime | None
    last_seen_at: datetime

    model_config = {"from_attributes": True}


class ReputationResponseDraftCreate(BaseModel):
    refresh: bool = False


class ReputationResponseDraftDecision(BaseModel):
    decision: Literal["approve", "reject"]
    approved_text: str | None = Field(default=None, max_length=600)


class ReputationResponsePublishRequest(BaseModel):
    confirmation_version: str = Field(..., min_length=1, max_length=80)
    confirm_publish_to_google: bool


class ReputationResponseExecutionControl(BaseModel):
    action: Literal["pause", "resume", "cancel", "retry"]


class ReputationReviewRequestCampaignCreate(BaseModel):
    campaign_id: str = Field(..., min_length=1, max_length=36)
    name: str = Field(default="", max_length=160)
    channel: Literal["email", "link", "qr", "kiosk", "sms"]
    subject: str | None = Field(default=None, max_length=180)
    message_body: str = Field(default="", max_length=700)
    review_url: str | None = Field(default=None, max_length=1200)


class ReputationReviewRequestRecipientCreate(BaseModel):
    email_address: str = Field(..., min_length=3, max_length=320)
    customer_name: str | None = Field(default=None, max_length=160)
    consent_basis: Literal[
        "explicit_opt_in",
        "existing_customer_relationship",
        "customer_requested",
    ]
    consent_source: str = Field(..., min_length=1, max_length=160)
    consent_confirmed: bool
    service_completed_at: datetime


class ReputationReviewRequestCampaignControl(BaseModel):
    action: Literal["activate", "pause", "complete", "cancel"]


class ReputationReviewRequestSuppressionCreate(BaseModel):
    reason: str = Field(default="Do not send review requests", max_length=160)
    source: str = Field(default="Account owner", max_length=120)
