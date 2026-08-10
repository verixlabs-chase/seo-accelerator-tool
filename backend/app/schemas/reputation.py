from datetime import datetime

from pydantic import BaseModel


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
