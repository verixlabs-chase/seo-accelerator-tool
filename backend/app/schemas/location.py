from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, Field, StringConstraints


NonBlankLocationName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]


class LocationCreateIn(BaseModel):
    name: NonBlankLocationName
    sub_account_id: str | None = Field(default=None, max_length=36)
    business_location_id: str | None = Field(default=None, max_length=36)
    campaign_id: str | None = Field(default=None, max_length=36)
    country_code: str = Field(default="US", min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class LocationUpdateRequest(BaseModel):
    name: Optional[NonBlankLocationName] = None
    business_location_id: Optional[str] = Field(default=None, max_length=36)


class LocationOut(BaseModel):
    id: str
    organization_id: str
    portfolio_id: str | None = None
    sub_account_id: str
    campaign_id: str | None = None
    location_code: str | None = None
    name: str
    country_code: str | None = None
    region: str | None = None
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    status: str | None = None
    business_location_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
